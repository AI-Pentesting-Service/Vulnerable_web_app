#!/bin/bash

echo "========================================"
echo "  CollabSpace - Starting Application"
echo "========================================"
echo ""

echo "Stopping any existing containers..."
docker compose down

echo ""
echo "Building and starting containers..."
docker compose up --build -d

echo ""
echo "Waiting for database to be ready..."
sleep 10

echo ""
echo "========================================"
echo "  CollabSpace is now running!"
echo "========================================"
echo ""
echo "Access the application at: http://localhost:8000"
echo ""
echo "Default accounts:"
echo "  Admin:   admin / Admin123!"
echo "  Manager: alice / Alice123!"
echo "  Member:  bob   / Bob123!"
echo ""
echo "To view logs: docker compose logs -f web"
echo "To stop: docker compose down"
echo ""
echo "========================================"
