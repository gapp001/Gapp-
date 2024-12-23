#!/bin/bash

git checkout $1 && git pull origin $1 &&

docker-compose up -d --build &&
docker system prune -f 
exit
