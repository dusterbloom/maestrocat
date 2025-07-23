# MaestroCat Web UI

This directory contains the modern web-based debug UI for MaestroCat.

## Features

- Real-time pipeline visualization with latency metrics
- Live conversation display
- Interactive configuration controls
- Module status monitoring
- Event logging
- Responsive design

## Development

The UI is built with vanilla HTML, CSS, and JavaScript with no external dependencies.

### File Structure

- `index.html` - Main HTML file
- `styles.css` - Styling
- `script.js` - Client-side JavaScript logic

### Integration

The UI connects to the MaestroCat backend via WebSocket at `ws://localhost:8080/ws` and uses the FastAPI endpoints for REST API calls.

## Deployment

The UI is automatically served by the MaestroCat debug server when placed in this directory.