from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import subprocess
import threading
import time
import os
import json
import queue
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.local')

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend calls

# Global variables to track agent process and streaming
agent_process = None
agent_status = "stopped"
event_queues = []  # Store SSE client queues
agent_data_queue = queue.Queue()  # Queue for agent data

@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({'status': 'healthy', 'agent_status': agent_status})

@app.route('/api/agent/start', methods=['POST'])
def start_agent():
    """Start the LiveKit voice agent"""
    global agent_process, agent_status
    
    if agent_process and agent_process.poll() is None:
        return jsonify({'status': 'already_running', 'message': 'Agent is already running'})
    
    try:
        # Start the agent in a separate process
        agent_process = subprocess.Popen([
            'uv', 'run', 'agent.py', 'console'
        ], cwd=os.path.dirname(__file__))
        
        agent_status = "starting"
        
        # Give it a moment to start
        time.sleep(2)
        
        if agent_process.poll() is None:
            agent_status = "running"
            return jsonify({'status': 'started', 'message': 'Agent started successfully'})
        else:
            agent_status = "failed"
            return jsonify({'status': 'error', 'message': 'Agent failed to start'}), 500
            
    except Exception as e:
        agent_status = "error"
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/agent/stop', methods=['POST'])
def stop_agent():
    """Stop the LiveKit voice agent"""
    global agent_process, agent_status
    
    if agent_process and agent_process.poll() is None:
        agent_process.terminate()
        agent_process.wait()
        agent_status = "stopped"
        return jsonify({'status': 'stopped', 'message': 'Agent stopped successfully'})
    else:
        agent_status = "stopped"
        return jsonify({'status': 'not_running', 'message': 'Agent was not running'})

@app.route('/api/agent/status', methods=['GET'])
def get_agent_status():
    """Get current agent status"""
    global agent_process, agent_status
    
    # Update status based on process state
    if agent_process:
        if agent_process.poll() is None:
            agent_status = "running"
        else:
            agent_status = "stopped"
    
    return jsonify({
        'status': agent_status,
        'process_id': agent_process.pid if agent_process and agent_process.poll() is None else None
    })

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get environment configuration (without secrets)"""
    return jsonify({
        'livekit_url': os.getenv('LIVEKIT_URL', 'Not configured'),
        'has_api_key': bool(os.getenv('LIVEKIT_API_KEY')),
        'has_api_secret': bool(os.getenv('LIVEKIT_API_SECRET')),
        'has_openai_key': bool(os.getenv('OPENAI_API_KEY')),
        'has_assemblyai_key': bool(os.getenv('ASSEMBLYAI_API_KEY')),
    })

@app.route('/api/stream', methods=['GET'])
def stream_agent_data():
    """Server-Sent Events endpoint for streaming agent data"""
    def event_stream():
        client_queue = queue.Queue()
        event_queues.append(client_queue)
        
        try:
            while True:
                try:
                    # Wait for data with timeout
                    data = client_queue.get(timeout=30)
                    yield f"data: {json.dumps(data)}\n\n"
                except queue.Empty:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
                except Exception as e:
                    print(f"Error in event stream: {e}")
                    break
        finally:
            # Clean up when client disconnects
            if client_queue in event_queues:
                event_queues.remove(client_queue)
    
    return Response(
        event_stream(),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control'
        }
    )

@app.route('/api/agent/data', methods=['POST'])
def receive_agent_data():
    """Endpoint for agent to send streaming data"""
    try:
        data = request.get_json()
        
        # Broadcast to all connected SSE clients
        for client_queue in event_queues[:]:  # Copy list to avoid modification during iteration
            try:
                client_queue.put_nowait(data)
            except queue.Full:
                # Remove clients with full queues (likely disconnected)
                event_queues.remove(client_queue)
        
        return jsonify({'status': 'received', 'clients_notified': len(event_queues)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask server for LiveKit Agent management...")
    print("Agent management endpoints:")
    print("  GET  /api/health - Health check")
    print("  POST /api/agent/start - Start agent")
    print("  POST /api/agent/stop - Stop agent") 
    print("  GET  /api/agent/status - Agent status")
    print("  GET  /api/config - Configuration check")
    print("Streaming endpoints:")
    print("  GET  /api/stream - Server-Sent Events stream")
    print("  POST /api/agent/data - Receive agent data")
    
    app.run(debug=True, port=5000)
