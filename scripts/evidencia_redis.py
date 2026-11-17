"""Evidencia de la caché Redis de Productos (criterio 3). Solo biblioteca estándar de Python.

Desde la raíz del repo, con el compose arriba (y sin sudo):
    python scripts/evidencia_redis.py demo     # miss, hit, expiración, invalidación (prueba 9), caída de Redis
    python scripts/evidencia_redis.py medir    # p50/p95 con y sin caché, tasa de aciertos, docker stats

Salidas en docs/evidencia/: redis-demo.log, redis-mediciones.json y redis-mediciones.log.
La contraseña del admin de demo y la de Redis se leen de .env y nunca se imprimen.

`demo` recrea Productos con CACHE_TTL_SEGUNDOS=8 para mostrar la expiración en segundos (mismo código,
otra configuración) y al final lo deja otra vez con el TTL por defecto (300 s).
Ambos modos crean productos propios ("Evidencia Redis …") y los desactivan al terminar.
"""
import http.client
import json
import random
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = RAIZ / "docs/evidencia"
PRODUCTOS = ("localhost", 8001)
CLIENTES = ("localhost", 8002)
REDIS = ("localhost", 6379)
TTL_DEMO = 8
lineas: list[str] = []


def log(msg: str = "") -> None:
    print(msg, flush=True)
    lineas.append(msg)


def leer_env() -> dict:
    env = {}
    for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            k, v = linea.split("=", 1)
            env[k.strip()] = v.strip()
    return env


# --- HTTP con conexión persistente (no se mide el establecimiento de TCP en cada petición) -------
class Api:
    def __init__(self, host_puerto, token: str | None = None):
        self.hp = host_puerto
        self.token = token
        self.conn = http.client.HTTPConnection(*host_puerto, timeout=10)

    def pedir(self, metodo: str, ruta: str, cuerpo: dict | None = None):
        cab = {"Content-Type": "application/json"}
        if self.token:
            cab["Authorization"] = f"Bearer {self.token}"
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        for intento in range(2):
            try:
                t0 = time.perf_counter()
                self.conn.request(metodo, ruta, body=datos, headers=cab)
                r = self.conn.getresponse()
                cuerpo_r = r.read()
                ms = (time.perf_counter() - t0) * 1000
                # Cabeceras en minúsculas: HTTP no distingue mayúsculas y uvicorn las envía en minúscula
                cabeceras = {k.lower(): v for k, v in r.getheaders()}
                return r.status, cabeceras, (json.loads(cuerpo_r) if cuerpo_r else None), ms
            except (ConnectionError, http.client.HTTPException, OSError):
                if intento:
                    raise
                self.conn.close()
                self.conn = http.client.HTTPConnection(*self.hp, timeout=10)


def token_admin(env: dict) -> str:
    _, _, cuerpo, _ = Api(CLIENTES).pedir("POST", "/auth/login",
                                          {"usuario": "admin", "password": env["DEMO_ADMIN_PASSWORD"]})
    return cuerpo["access_token"]


# --- Cliente mínimo del protocolo de Redis (RESP), para inspeccionar claves sin dependencias -----
class RedisMinimo:
    def __init__(self, password: str):
        self.password = password

    def cmd(self, *partes) -> object:
        with socket.create_connection(REDIS, timeout=2) as s:
            f = s.makefile("rb")
            for comando in (("AUTH", self.password), partes):
                msg = f"*{len(comando)}\r\n" + "".join(f"${len(str(p).encode())}\r\n{p}\r\n" for p in comando)
                s.sendall(msg.encode())
                respuesta = self._leer(f)
            return respuesta

    def _leer(self, f):
        linea = f.readline().decode().rstrip("\r\n")
        tipo, resto = linea[0], linea[1:]
        if tipo == "+":
            return resto
        if tipo == "-":
            raise RuntimeError(resto)
        if tipo == ":":
            return int(resto)
        if tipo == "$":
            n = int(resto)
            return None if n < 0 else f.read(n + 2)[:-2].decode()
        if tipo == "*":
            return [self._leer(f) for _ in range(int(resto))]
        raise RuntimeError(f"respuesta RESP desconocida: {linea}")

    def info(self, seccion: str) -> dict:
        texto = self.cmd("INFO", seccion)
        return dict(l.split(":", 1) for l in texto.splitlines() if ":" in l)


def clave(pid: int) -> str:
    return f"productos:v1:{pid}"


# --- Docker ----------------------------------------------------------------------------------------
def compose(*args: str, env_extra: dict | None = None, mostrar: bool = True) -> str:
    import os
    env = dict(os.environ, **(env_extra or {}))
    if mostrar:
        pref = " ".join(f"{k}={v}" for k, v in (env_extra or {}).items())
        log(f"  $ {pref + ' ' if pref else ''}docker compose {' '.join(args)}")
    r = subprocess.run(["docker", "compose", *args], cwd=RAIZ, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"Falló docker compose {' '.join(args)}:\n{r.stderr}")
    return r.stdout


def esperar_health(api: Api, segundos: int = 60) -> dict:
    for _ in range(segundos * 2):
        try:
            estado, _, cuerpo, _ = api.pedir("GET", "/health")
            if estado == 200:
                return cuerpo
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit("Productos no respondió /health")


def recrear_productos(ttl: int | None, api: Api) -> None:
    compose("up", "-d", "--no-deps", "--force-recreate", "productos",
            env_extra={"CACHE_TTL_SEGUNDOS": str(ttl)} if ttl else None)
    time.sleep(1)
    esperar_health(api)


def guardar(nombre: str) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / nombre).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"\nEvidencia guardada en {SALIDA / nombre}")


# ==================================================================================================
def demo() -> int:
    env = leer_env()
    r = RedisMinimo(env["REDIS_PASSWORD"])
    api = Api(PRODUCTOS, token_admin(env))
    inicio = datetime.now(timezone.utc)
    log(f"Evidencia de caché Redis en Productos — {inicio.isoformat(timespec='seconds')}")

    def get(pid, etiqueta=""):
        estado, cab, cuerpo, ms = api.pedir("GET", f"/productos/{pid}")
        log(f"  GET /productos/{pid} -> {estado}  X-Cache: {cab.get('x-cache', '-'):4s}  "
            f"precio={cuerpo.get('precio_cop') if cuerpo else '-'}  version={cuerpo.get('version') if cuerpo else '-'}"
            f"  {ms:6.1f} ms {etiqueta}")
        return estado, cab.get("x-cache"), cuerpo

    def en_redis(pid):
        existe = r.cmd("EXISTS", clave(pid))
        ttl = r.cmd("TTL", clave(pid))
        log(f"  Redis: EXISTS {clave(pid)} = {existe}" + (f", TTL = {ttl} s" if existe else ""))
        return existe

    resultados = {}
    pid = None
    try:
        log(f"\n0. Productos con TTL de {TTL_DEMO} s para ver la expiración en vivo")
        recrear_productos(TTL_DEMO, api)
        _, _, p, _ = api.pedir("POST", "/productos", {"nombre": f"Evidencia Redis {inicio:%H%M%S}",
                                                      "categoria": "evidencia", "precio_cop": 1_000_000})
        pid = p["id"]
        log(f"  Producto de prueba creado: id {pid}")

        log("\n1. MISS: primera consulta (no está en Redis; se lee de PostgreSQL y se guarda con TTL)")
        en_redis(pid)
        _, c1, _ = get(pid)
        en_redis(pid)
        log("\n2. HIT: segunda consulta (se responde desde Redis)")
        _, c2, _ = get(pid)
        resultados["miss_hit"] = c1 == "MISS" and c2 == "HIT"

        log(f"\n3. EXPIRACIÓN: se esperan {TTL_DEMO + 1} s sin tocar el producto")
        time.sleep(TTL_DEMO + 1)
        existe = en_redis(pid)
        _, c3, _ = get(pid)
        resultados["expiracion"] = existe == 0 and c3 == "MISS"

        log("\n4. INVALIDACIÓN (prueba 9): cambio de precio con el producto en caché")
        get(pid)
        en_redis(pid)
        estado, _, nuevo, _ = api.pedir("PUT", f"/productos/{pid}", {"precio_cop": 1_250_000})
        log(f"  PUT /productos/{pid} precio_cop=1250000 -> {estado}, version {nuevo['version']}")
        existe = en_redis(pid)
        _, c4, cuerpo = get(pid, "<- precio nuevo, no el viejo")
        _, _, cot, _ = api.pedir("GET", f"/productos/{pid}/cotizacion")
        log(f"  GET /productos/{pid}/cotizacion -> precio={cot['precio_cop']} version={cot['version']} "
            "(la cotización siempre lee PostgreSQL)")
        resultados["invalidacion"] = (existe == 0 and c4 == "MISS" and cuerpo["precio_cop"] == 1_250_000
                                      and cot["precio_cop"] == 1_250_000)

        log("\n5. CAÍDA DE REDIS: la API sigue respondiendo desde PostgreSQL")
        compose("stop", "redis")
        estado, c5, _ = get(pid, "<- primera tras la caída: paga el timeout de 100 ms")
        estado2, c6, _ = get(pid, "<- en pausa: ni intenta Redis")
        estado3, _, act, _ = api.pedir("PUT", f"/productos/{pid}", {"precio_cop": 1_300_000})
        log(f"  PUT /productos/{pid} precio_cop=1300000 con Redis caído -> {estado3} (invalidación fallida, "
            "registrada en el log)")
        salud = esperar_health(api)
        log(f"  /health -> database={salud['database']}, redis={salud['redis']}")
        resultados["caida"] = estado == 200 and estado2 == 200 and estado3 == 200 and c5 == "MISS"

        log("\n6. RECUPERACIÓN: Redis vuelve y la caché se usa de nuevo, sin reiniciar Productos")
        compose("start", "redis")
        for _ in range(40):
            try:
                if r.cmd("PING") == "PONG":
                    break
            except OSError:
                time.sleep(0.5)
        log("  Redis responde PONG (y recargó del disco la clave con el precio VIEJO); "
            "se espera a que venza la pausa de 5 s")
        log(f"  Redis: GET {clave(pid)} -> precio en caché = "
            f"{json.loads(r.cmd('GET', clave(pid)) or 'null') and json.loads(r.cmd('GET', clave(pid)))['precio_cop']}")
        time.sleep(5.5)
        _, c7, cuerpo = get(pid, "<- borra la invalidación pendiente y lee PostgreSQL")
        _, c8, _ = get(pid)
        resultados["recuperacion"] = c7 == "MISS" and c8 == "HIT" and cuerpo["precio_cop"] == 1_300_000

        log("\n7. Líneas de log de Productos (una por consulta, más los avisos de Redis)")
        salida = compose("logs", "--no-log-prefix", "--since", inicio.isoformat(), "productos", mostrar=False)
        for linea in salida.splitlines():
            if (f"producto_id={pid} " in linea or "redis no disponible" in linea
                    or "no se pudo invalidar" in linea or "pendientes aplicadas" in linea):
                log(f"  {linea}")
    finally:
        log("\n8. Limpieza: se desactiva el producto de prueba y Productos vuelve al TTL por defecto")
        try:
            compose("start", "redis", mostrar=False)
        except SystemExit:
            pass
        if pid is not None:
            api.pedir("DELETE", f"/productos/{pid}")
        recrear_productos(None, api)
        log(f"  /health -> {esperar_health(api)}")

    log("\nResumen")
    for k, v in resultados.items():
        log(f"  {k:14s} {'OK' if v else 'FALLA'}")
    ok = len(resultados) == 5 and all(resultados.values())
    log(f"\nEVIDENCIA REDIS {'COMPLETA' if ok else 'CON FALLAS'}")
    guardar("redis-demo.log")
    return 0 if ok else 1


# ==================================================================================================
def percentiles(ms: list[float]) -> dict:
    q = statistics.quantiles(ms, n=100, method="inclusive")
    return {"n": len(ms), "p50_ms": round(q[49], 2), "p95_ms": round(q[94], 2), "p99_ms": round(q[98], 2),
            "media_ms": round(statistics.fmean(ms), 2)}


def docker_stats() -> list[dict]:
    r = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}"], cwd=RAIZ,
                       capture_output=True, text=True)
    filas = [json.loads(l) for l in r.stdout.splitlines() if l.strip()]
    return [{"contenedor": f["Name"], "cpu": f["CPUPerc"], "memoria": f["MemUsage"]}
            for f in filas if any(s in f["Name"] for s in ("redis", "productos", "postgres"))]


def medir(n: int = 1000) -> int:
    env = leer_env()
    r = RedisMinimo(env["REDIS_PASSWORD"])
    api = Api(PRODUCTOS, token_admin(env))
    salud = esperar_health(api)
    if salud.get("redis") != "ok":
        log("Redis no está disponible: levántalo antes de medir (docker compose start redis)")
        return 1
    inicio = datetime.now(timezone.utc)
    log(f"Mediciones de la caché Redis — {inicio.isoformat(timespec='seconds')}")
    log(f"Cliente: conexión HTTP persistente a localhost:8001, token de admin, {n} peticiones por escenario.")
    creados = []
    try:
        for i in range(10):
            _, _, p, _ = api.pedir("POST", "/productos", {"nombre": f"Evidencia Redis medición {i}",
                                                          "categoria": "evidencia",
                                                          "precio_cop": 1_000_000 + i * 50_000})
            creados.append(p["id"])
        pid = creados[0]
        for _ in range(50):  # calentamiento: conexiones del pool, JIT de rutas, etc.
            api.pedir("GET", f"/productos/{pid}")
            api.pedir("GET", f"/productos/{pid}/cotizacion")

        # 1) Con caché: siempre HIT
        api.pedir("GET", f"/productos/{pid}")
        hit, cabeceras = [], set()
        for _ in range(n):
            _, cab, _, ms = api.pedir("GET", f"/productos/{pid}")
            hit.append(ms)
            cabeceras.add(cab.get("x-cache"))
        assert cabeceras == {"HIT"}, cabeceras

        # 2) Sin caché: se borra la clave ANTES de cada petición (fuera del tiempo medido) -> siempre MISS
        miss = []
        for _ in range(n):
            r.cmd("DEL", clave(pid))
            _, cab, _, ms = api.pedir("GET", f"/productos/{pid}")
            assert cab.get("x-cache") == "MISS"
            miss.append(ms)

        # 3) Referencia: cotización (solo PostgreSQL, sin tocar Redis)
        cot = [api.pedir("GET", f"/productos/{pid}/cotizacion")[3] for _ in range(n)]

        # 4) Tasa de aciertos con una carga mixta: 10 productos con popularidad desigual (Zipf),
        #    y un cambio de precio cada 100 lecturas (invalida un producto).
        rng = random.Random(42)
        pesos = [1 / (k + 1) for k in range(len(creados))]
        for p_ in creados:
            r.cmd("DEL", clave(p_))
        antes = r.info("stats")
        cuenta = {"HIT": 0, "MISS": 0}
        lecturas = 2000
        stats_carga: list[dict] = []
        import threading
        hilo = threading.Thread(target=lambda: (time.sleep(0.3), stats_carga.extend(docker_stats())))
        hilo.start()  # docker stats DURANTE la carga (tarda ~2 s en muestrear)
        for i in range(lecturas):
            elegido = rng.choices(creados, weights=pesos)[0]
            _, cab, _, _ = api.pedir("GET", f"/productos/{elegido}")
            cuenta[cab["x-cache"]] += 1
            if i % 100 == 99:
                cambiar = rng.choice(creados)
                api.pedir("PUT", f"/productos/{cambiar}", {"precio_cop": 900_000 + rng.randint(0, 900) * 1000})
        hilo.join()
        despues = r.info("stats")
        redis_hits = int(despues["keyspace_hits"]) - int(antes["keyspace_hits"])
        redis_miss = int(despues["keyspace_misses"]) - int(antes["keyspace_misses"])
        memoria = r.info("memory")
        stats = docker_stats()
        # Lado servidor: duracion_ms de la línea de log de cada consulta (sin HTTP ni validación del JWT)
        servidor = {"HIT": [], "MISS": []}
        for linea in compose("logs", "--no-log-prefix", "--since", inicio.isoformat(), "productos",
                             mostrar=False).splitlines():
            if "consulta producto_id=" in linea and "duracion_ms=" in linea:
                tipo = "HIT" if "cache=HIT" in linea else "MISS"
                servidor[tipo].append(float(linea.rsplit("duracion_ms=", 1)[1]))
    finally:
        for p_ in creados:
            api.pedir("DELETE", f"/productos/{p_}")

    res = {
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "peticiones_por_escenario": n,
        "con_cache_hit": percentiles(hit),
        "sin_cache_miss": percentiles(miss),
        "cotizacion_solo_postgres": percentiles(cot),
        "servidor_hit": percentiles(servidor["HIT"]),
        "servidor_miss": percentiles(servidor["MISS"]),
        "carga_mixta": {"lecturas": lecturas, "cambios_de_precio": lecturas // 100,
                        "hit": cuenta["HIT"], "miss": cuenta["MISS"],
                        "tasa_aciertos": round(cuenta["HIT"] / lecturas, 4),
                        "redis_keyspace_hits": redis_hits, "redis_keyspace_misses": redis_miss},
        "redis_memoria": {"used_memory_human": memoria.get("used_memory_human"),
                          "used_memory_peak_human": memoria.get("used_memory_peak_human")},
        "docker_stats_durante_carga": stats_carga,
        "docker_stats_reposo": stats,
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "redis-mediciones.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n",
                                                  encoding="utf-8")
    log("\n| Escenario | n | p50 (ms) | p95 (ms) | p99 (ms) | media (ms) |")
    log("|---|---|---|---|---|---|")
    for nombre, k in [("Con caché (HIT)", "con_cache_hit"), ("Sin caché (MISS forzado)", "sin_cache_miss"),
                      ("Cotización (solo PostgreSQL)", "cotizacion_solo_postgres")]:
        m = res[k]
        log(f"| {nombre} | {m['n']} | {m['p50_ms']} | {m['p95_ms']} | {m['p99_ms']} | {m['media_ms']} |")
    log("\nLado servidor (duracion_ms del log: lectura Redis o PostgreSQL + serialización, sin HTTP ni JWT):")
    log("| Resultado | n | p50 (ms) | p95 (ms) | p99 (ms) |")
    log("|---|---|---|---|---|")
    for nombre, k in [("HIT", "servidor_hit"), ("MISS", "servidor_miss")]:
        m = res[k]
        log(f"| {nombre} | {m['n']} | {m['p50_ms']} | {m['p95_ms']} | {m['p99_ms']} |")
    c = res["carga_mixta"]
    log(f"\nCarga mixta: {c['lecturas']} lecturas, {c['cambios_de_precio']} cambios de precio -> "
        f"{c['hit']} HIT / {c['miss']} MISS = tasa de aciertos {c['tasa_aciertos']:.1%} "
        f"(Redis: keyspace_hits {redis_hits}, keyspace_misses {redis_miss})")
    log(f"Memoria de Redis: {res['redis_memoria']['used_memory_human']}")
    for titulo, filas in [("durante la carga mixta", stats_carga), ("en reposo, al terminar", stats)]:
        log(f"docker stats {titulo}:")
        for s in filas:
            log(f"  {s['contenedor']:32s} CPU {s['cpu']:>7s}  memoria {s['memoria']}")
    guardar("redis-mediciones.log")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("demo", "medir"):
        print(__doc__)
        sys.exit(1)
    sys.exit(demo() if sys.argv[1] == "demo" else medir())
