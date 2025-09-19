from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import threading
import time
import os
import uuid
from dotenv import load_dotenv
import subprocess
import tempfile

from livekit import api, agents
from livekit.api import AccessToken, VideoGrant, RoomServiceClient
from livekit.agents import Worker, WorkerOptions

# Load environment variables
load_dotenv('.env.local')

app = Flask(__name__)
CORS(app)

# LiveKit configuration
LIVEKIT_URL = os.getenv('LIVEKIT_URL')
LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET')

# Global variables for tracking
active_rooms = {}
active_agents = {}

class RoomManager:
    def __init__(self):
        self.room_service = RoomServiceClient(
            LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
        )
    
    async def create_room_with_agent(self, user_name="user"):
        """Create a room and start an agent in it"""
        room_name = f"voice_room_{uuid.uuid4().hex[:8]}"
        participant_identity = f"user_{uuid.uuid4().hex[:8]}"
        
        try:
            # 1. Create the room
            room = await self.room_service.create_room(
                api.CreateRoomRequest(name=room_name)
            )
            
            # 2. Generate user token
            user_token = self.create_participant_token(
                participant_identity, user_name, room_name
            )
            
            # 3. Start agent in this room
            agent_worker = await self.start_agent_in_room(room_name)
            
            # Track the room and agent
            active_rooms[room_name] = {
                'room': room,
                'agent_worker': agent_worker,
                'created_at': time.time()
            }
            
            return {
                'room_name': room_name,
                'server_url': LIVEKIT_URL,
                'participant_token': user_token,
                'participant_name': user_name,
                'participant_identity': participant_identity
            }
            
        except Exception as e:
            raise Exception(f"Failed to create room with agent: {str(e)}")
    
    def create_participant_token(self, identity, name, room_name):
        """Create access token for a participant"""
        token = AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        token.identity = identity
        token.name = name
        token.ttl = 3600  # 1 hour
        
        grant = VideoGrant(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True
        )
        token.add_grant(grant)
        
        return token.to_jwt()
    
    async def start_agent_in_room(self, room_name):
        """Start a voice agent in the specified room"""
        try:
            # Import your agent entrypoint
            from enhanced_agent import entrypoint
            
            # Create worker for this specific room
            worker = Worker(
                WorkerOptions(
                    entrypoint_fnc=entrypoint,
                    # Configure worker to join specific room
                    room_name=room_name
                )
            )
            
            # Start the worker in a background task
            def run_worker():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(worker.start())
            
            worker_thread = threading.Thread(target=run_worker, daemon=True)
            worker_thread.start()
            
            # Give it a moment to start
            await asyncio.sleep(2)
            
            return worker
            
        except Exception as e:
            raise Exception(f"Failed to start agent in room: {str(e)}")
    
    async def cleanup_room(self, room_name):
        """Clean up room and stop agent"""
        if room_name in active_rooms:
            room_data = active_rooms[room_name]
            
            # Stop the agent worker
            if 'agent_worker' in room_data:
                try:
                    await room_data['agent_worker'].shutdown()
                except:
                    pass
            
            # Delete the room
            try:
                await self.room_service.delete_room(
                    api.DeleteRoomRequest(room=room_name)
                )
            except:
                pass
            
            # Remove from tracking
            del active_rooms[room_name]

room_manager = RoomManager()

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'active_rooms': len(active_rooms),
        'livekit_configured': bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET)
    })

@app.route('/api/create-voice-session', methods=['POST'])
def create_voice_session():
    """Create a new voice session with room and agent"""
    try:
        data = request.get_json() or {}
        user_name = data.get('user_name', 'User')
        
        # Create room with agent asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        session_details = loop.run_until_complete(
            room_manager.create_room_with_agent(user_name)
        )
        
        return jsonify({
            'success': True,
            'session': session_details,
            'message': 'Voice session created successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/end-voice-session', methods=['POST'])
def end_voice_session():
    """End a voice session and cleanup"""
    try:
        data = request.get_json()
        room_name = data.get('room_name')
        
        if not room_name:
            return jsonify({'success': False, 'error': 'Room name required'}), 400
        
        # Cleanup room and agent
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(room_manager.cleanup_room(room_name))
        
        return jsonify({
            'success': True,
            'message': 'Voice session ended successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/sessions', methods=['GET'])
def list_active_sessions():
    """List all active voice sessions"""
    sessions = []
    for room_name, room_data in active_rooms.items():
        sessions.append({
            'room_name': room_name,
            'created_at': room_data['created_at'],
            'duration': time.time() - room_data['created_at']
        })
    
    return jsonify({
        'active_sessions': sessions,
        'count': len(sessions)
    })

@app.route('/api/voice-capabilities', methods=['GET'])
def get_voice_capabilities():
    """Get available voice AI capabilities"""
    return jsonify({
        'stt_provider': 'AssemblyAI',
        'llm_provider': 'OpenAI GPT-4o-mini',
        'tts_provider': 'Rime',
        'vad_enabled': True,
        'turn_detection': True,
        'noise_cancellation': True,
        'supported_languages': ['en', 'es', 'fr', 'de', 'it', 'pt', 'zh']
    })

if __name__ == '__main__':
    print("🎙️  Voice AI Room Manager Starting...")
    print(f"LiveKit URL: {LIVEKIT_URL}")
    print(f"API configured: {bool(LIVEKIT_API_KEY and LIVEKIT_API_SECRET)}")
    print("\nEndpoints:")
    print("  POST /api/create-voice-session - Create room + agent")
    print("  POST /api/end-voice-session - Cleanup session") 
    print("  GET  /api/sessions - List active sessions")
    print("  GET  /api/voice-capabilities - Available features")
    print("  GET  /api/health - Health check")
    
    app.run(debug=True, port=5000)
