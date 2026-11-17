#export COMPOSE_PARALLEL_LIMIT=10 
export COMPOSE_HTTP_TIMEOUT=200


docker compose -f Xel.yml up --no-recreate #no elimina contenedores ya existentes