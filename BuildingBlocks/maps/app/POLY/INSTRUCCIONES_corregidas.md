===========================================================
GUÍA DE INICIO: PROYECTO DE GEOVISOR (AGBR)
===========================================================

instrucciones 

-----------------------------------------------------------
1.  ANTES DE EMPEZAR (Requisitos)
-----------------------------------------------------------
Para que el script funcione correctamente, asegúrate de tener 
instalado Python 3 y las siguientes librerías:

  • geopandas (para el manejo de mapas)
  • pandas    (para procesar tus archivos CSV)
  • plotly    (para que el mapa sea interactivo y visual)
  • shapely   (para cálculos de geometría)

¿Cómo instalarlas rápido? Solo copia y pega esto en tu terminal:
> pip install geopandas pandas plotly shapely

-----------------------------------------------------------

-----------------------------------------------------------
3.  ¿CÓMO USAR EL SCRIPT?
-----------------------------------------------------------
El script recibe instrucciones a través de la consola. Aquí 
tienes un ejemplo de cómo "pedirle" que haga un mapa:

python Map.py datos.csv ./salida "cvegeo" "municipio" "casos" "15" "Mi Mapa"

¿Qué significa cada cosa?
- datos.csv: Tu archivo con información.
- ./salida:  Donde quieres que se guarde el mapa (.html).
- "cvegeo":  La columna que tiene las claves del INEGI.
- "15":      El ID del estado (en este caso, Estado de México).

-----------------------------------------------------------
4.  NOTAS ADICIONALES
-----------------------------------------------------------
• El resultado final será un archivo llamado "mapa.html". 
  Solo dale doble clic y podrás verlo en Chrome, Edge o Safari.
• Si el script no encuentra un estado específico, usará el 
  centro por defecto para que el proceso no se detenga.

Cualquier duda técnica o ajuste que necesites, no dudes en 
contactarme. ¡Espero que esta herramienta sea de gran utilidad!

-----------------------------------------------------------
