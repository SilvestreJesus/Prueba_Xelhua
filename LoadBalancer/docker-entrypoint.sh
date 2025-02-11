#!/bin/sh

# Definir rutas absolutas para los archivos de configuración
CONF_DIR="/etc/nginx"
CONF_TEMPLATE="$CONF_DIR/nginx.template.conf"
CONF_BACKENDS="$CONF_DIR/backend_servers.conf"
CONF_FINAL="$CONF_DIR/nginx.conf"

# Verificar si la variable BACKENDS está definida
if [ -z "$BACKENDS" ]; then
    echo "❌ No se han definido nodos backend en la variable BACKENDS."
    exit 1
fi

# Asegurar que el directorio de configuración de Nginx existe
mkdir -p "$CONF_DIR"

# Limpiar cualquier configuración previa
rm -f "$CONF_BACKENDS" "$CONF_FINAL"

# Crear el archivo de configuración para los backends
echo "# Configuración dinámica de upstream para Nginx" > "$CONF_BACKENDS"

# Separar la variable BACKENDS por comas y agregar los servidores al archivo de configuración
IFS=','
for backend in $BACKENDS; do
    echo "server $backend;" >> "$CONF_BACKENDS"
done

echo "✅ Configuración generada en $CONF_BACKENDS:"
cat "$CONF_BACKENDS"

# Verificar que el archivo de plantilla existe antes de procesarlo
if [ ! -f "$CONF_TEMPLATE" ]; then
    echo "❌ Error: El archivo de plantilla $CONF_TEMPLATE no existe."
    exit 1
fi

# Reemplazar las variables de entorno en el archivo de configuración de Nginx
envsubst < "$CONF_TEMPLATE" > "$CONF_FINAL"

# Verificar que el archivo final se generó correctamente
if [ ! -s "$CONF_FINAL" ]; then
    echo "❌ Error: El archivo final de configuración de Nginx está vacío."
    exit 1
fi

# Mostrar el contenido del archivo final para depuración
echo "✅ Configuración final de Nginx generada en $CONF_FINAL:"
cat "$CONF_FINAL"

# Ejecutar Nginx en primer plano
exec nginx -g 'daemon off;'
