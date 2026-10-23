#!/bin/bash

# Wait for the frontend service to be ready (port 5183)
while ! nc -z localhost 5183; do   
  sleep 1
done

# Launch Firefox in a new window to the HIAS dashboard
firefox --new-window http://localhost:5183 &
