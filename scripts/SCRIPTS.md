# Scripts de Arranque — GenAI Grader

Estos scripts gestionan el despliegue del proyecto en una máquina local usando
**tmux** para sesiones persistentes, **ngrok** para exponer el servicio a internet
y **gunicorn** como servidor web. La BD es **SQLite** con modo WAL.

## Requisitos previos

- `tmux` instalado en el host
- `ngrok` configurado con un tunnel llamado `backend`
- `uv` para gestión de dependencias
- Ollama corriendo en el host

---

## Tabla resumen

| Script | Propósito | ¿Qué arranca? |
|--------|-----------|---------------|
| `start_genaigrader.sh` | Arranque completo | tmux + ngrok + ollama + gunicorn + **qcluster** |
| `stop_genaigrader.sh` | Parada completa | Para gunicorn, ollama, ngrok, **qcluster**, cierra tmux |
| `restart_gunicorn.sh` | Despliegue de nueva versión | Para gunicorn, **qcluster**, collectstatic, relanza ambos |
| `migrate_sqlite_to_postgres.sh` | Migración única de datos | Nada en tmux: vuelca el SQLite a la PostgreSQL de producción Docker |

---

## `start_genaigrader.sh`

**Propósito:** Arrancar todo el stack desde cero.

**Flujo de ejecución:**

1. Crea sesión tmux `genaigrader` si no existe
2. Lanza ngrok en background (`ngrok start --all`)
3. Extrae la URL pública de ngrok vía API local (`localhost:4040/api/tunnels`)
4. Escribe `.env.django` con `DJANGO_ALLOWED_HOSTS=<URL de ngrok>,localhost`
5. Lanza Ollama en background (`ollama serve`)
6. Ejecuta `collectstatic`
7. Lanza gunicorn en tmux pane 1:

   ```bash
   uv run gunicorn mi_web.wsgi:application \
       --bind 127.0.0.1:9898 \
       --log-file gunicorn.log \
       --pid gunicorn.pid \
       --timeout 6000 \
       --env DJANGO_SETTINGS_MODULE=mi_web.settings_ngrok
   ```

8. **NUEVO:** Crea un split vertical en tmux (pane 2) y lanza `qcluster`:

   ```bash
   uv run manage.py qcluster --settings=mi_web.settings_ngrok
   ```

   - `qcluster` es el worker de Django Q2 que consume la cola de tareas.
   - Corre en un pane separado para que sus logs sean visibles.

### Configuración

Las variables editables están al inicio del script:

```bash
SESSION_NAME="genaigrader"       # nombre de la sesión tmux
PORT=9898                        # puerto local de gunicorn
PROJECT_DIR="$HOME/genaigrader"  # ruta del proyecto
SETTINGS_MODULE="mi_web.settings_ngrok"
```

---

## `stop_genaigrader.sh`

**Propósito:** Parar todo el stack limpiamente.

**Flujo de ejecución:**

1. Para gunicorn usando `gunicorn.pid`
2. Para Ollama usando `ollama.pid`
3. Envía `pkill ngrok` a tmux
4. **NUEVO:** Para `qcluster` con `pkill -f "manage.py qcluster"`
5. Cierra la sesión tmux

---

## `restart_gunicorn.sh`

**Propósito:** Desplegar una nueva versión del código sin reiniciar Ollama ni ngrok.

**Flujo:**

1. Para gunicorn (usando `gunicorn.pid`)
2. Recolecta la URL pública de ngrok vía API
3. Regenera `.env.django` con la URL actualizada
4. Ejecuta `collectstatic`
5. Relanza gunicorn en tmux pane 1
6. **NUEVO:** Para `qcluster` con `pkill`, espera 1s, crea split vertical y relanza:

   ```bash
   uv run manage.py qcluster --settings=mi_web.settings_ngrok
   ```

---

## `migrate_sqlite_to_postgres.sh`

**Propósito:** pasar los datos del viejo `db.sqlite3` (este entorno de
tmux/ngrok) a la PostgreSQL **vacía** del `docker-compose.prod.yml`. Es de
**un solo uso**; no arranca ni para nada de este entorno (hay que pararlo
antes con `stop_genaigrader.sh`).

```bash
./scripts/migrate_sqlite_to_postgres.sh          # destino vacío
./scripts/migrate_sqlite_to_postgres.sh --reset  # borra antes los volúmenes de prod
```

Documentación completa: [MIGRACION.md](MIGRACION.md).

---

## ¿Por qué se necesita `qcluster`?

Django Q2 necesita un worker separado (`qcluster`) para procesar las tareas
en segundo plano. Sin él:

- Las evaluaciones de exámenes se quedarían encoladas sin ejecutarse
- Las descargas de modelos quedarían pendientes para siempre
- El frontend mostraría "Queued" y nunca avanzaría

Con `qcluster` corriendo:

- Las evaluaciones se procesan de forma asíncrona
- El servidor web no se bloquea durante las llamadas al LLM
- El frontend recibe actualizaciones en tiempo real por pregunta

### Modo SQLite + WAL

El proyecto usa `PRAGMA journal_mode=WAL` en SQLite para permitir que gunicorn
escriba mientras `qcluster` lee/escribe concurrentemente. Sin WAL mode, SQLite
bloquearía la BD en cada escritura concurrente.

---

## Cómo verificar que funciona

1. Arranca con `./scripts/start_genaigrader.sh`
2. Conéctate a tmux: `tmux attach -t genaigrader`
3. Deberías ver dos paneles: gunicorn arriba, `qcluster` abajo con logs como:
   ```
   [Q] INFO MainProcess ready for work at ...
   ```
4. Sube un examen desde la web. El log de `qcluster` debe mostrar:
   ```
   [Q] INFO Enqueued [genaigrader] 1
   [Q] INFO MainProcess processing ...
   ```

Para salir de tmux sin cerrar nada: `Ctrl+b` luego `d` (detach).

---

## Solución de problemas

### `qcluster` no arranca

Verifica que el virtualenv esté creado:
```bash
cd $PROJECT_DIR && uv sync
```

### Tareas encoladas pero no se procesan

Comprueba que `qcluster` está corriendo:
```bash
tmux attach -t genaigrader
```
Si el pane inferior no existe o muestra errores, relanza manualmente:
```bash
set -a; source .env.django; set +a
uv run manage.py qcluster --settings=mi_web.settings_ngrok
```

### "database is locked"

SQLite no soporta múltiples escritores simultáneos. Si ocurre:
- Reduce los workers de gunicorn a 1: añade `--workers 1` al comando gunicorn
- O migra a PostgreSQL (`DATABASE_URL=postgres://...`)
