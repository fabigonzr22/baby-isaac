# Baby Isaac — Wishlist 🎁

Aplicación web para el baby shower de Isaac. Permite a los invitados ver la
wishlist, reservar un regalo con su nombre, recibir los datos de pago (Binance)
y quedar "pendiente de confirmación". Incluye un panel privado para Fabi.

## Arquitectura

- **Página pública** (`/`): portada → wishlist → filtros por categoría → producto → "Quiero regalarlo" → nombre → confirmación → datos Binance → aviso de pendiente.
- **Panel privado** (`/admin`): login → dashboard → regalos disponibles/reservados/pagados → quién regaló cada cosa → confirmar pago → agregar/editar/eliminar regalos.
- **Base de datos SQLite**: `productos`, `regaladores`, `reservas`, con estados `available → reserved → paid`.

## Ejecutar en local

```bash
pip install -r requirements.txt
python app.py
```

Abre http://localhost:5000

## Despliegue (Render)

1. Sube este proyecto a un repositorio de GitHub.
2. En [render.com](https://render.com) → **New → Web Service** → conecta el repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
5. Añade la variable de entorno `SECRET_KEY` (cualquier texto largo y aleatorio).

## Despliegue (Railway)

1. `railway init` en esta carpeta y conecta el repo.
2. Railway detecta `requirements.txt` automáticamente.
3. Añade `SECRET_KEY` en Variables.

## Configuración

Variables de entorno opcionales:

| Variable | Descripción | Default |
|---|---|---|
| `ADMIN_USER` | Usuario del panel privado | `fabi` |
| `ADMIN_PASSWORD` | Contraseña del panel | `isaac2026` |
| `BINANCE_DATA` | Datos de pago a mostrar (multilínea) | placeholder |
| `SECRET_KEY` | Clave de sesión Flask | aleatoria |

> ⚠️ **Importante**: cambia `ADMIN_PASSWORD` en producción (variable de entorno).

Para editar los datos de Binance, cambia el bloque `BINANCE_DATA` en `app.py`
o define la variable `BINANCE_DATA` en el hosting.

## Estado del regalo

- `available` → visible y reservable.
- `reserved` → alguien lo reservó; queda pendiente de pago.
- `paid` → confirmado por Fabi en el panel.

El flujo de reserva es atómico: si dos personas intentan reservar el mismo
regalo, solo la primera lo logra.
