#!/bin/bash

# Health check endpoint
python3 -m http.server 8080 --directory /app &
HEALTH_PID=$!

# Start the bot
python3 bot.py

# Cleanup
kill $HEALTH_PID
