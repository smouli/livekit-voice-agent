import os
import time
from dotenv import load_dotenv
import json
import aiohttp

from livekit import agents, rtc
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    openai,
    assemblyai,
    rime,
    silero,
    noise_cancellation,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# Load environment variables from .env.local in the same directory
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, ".env.local")
load_dotenv(env_path)


class EnhancedAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="You are a helpful voice AI assistant.")
        self.session_data = {}

    async def on_data_received(self, data: rtc.DataPacket):
        """Handle data messages from frontend"""
        try:
            message = json.loads(data.data.decode())
            message_type = message.get("type")
            
            if message_type == "get_status":
                # Send agent status back to frontend
                await self.send_data_to_frontend({
                    "type": "status_response",
                    "status": "active",
                    "session_data": self.session_data
                })
            
            elif message_type == "update_instructions":
                # Update agent instructions from frontend
                new_instructions = message.get("instructions")
                if new_instructions:
                    self.instructions = new_instructions
                    await self.send_data_to_frontend({
                        "type": "instructions_updated",
                        "instructions": new_instructions
                    })
            
            elif message_type == "get_conversation_history":
                # Send conversation history to frontend
                await self.send_data_to_frontend({
                    "type": "conversation_history",
                    "history": self.session_data.get("messages", [])
                })
                
        except Exception as e:
            print(f"Error handling data message: {e}")

    async def send_data_to_frontend(self, data: dict):
        """Send data message to frontend via LiveKit and Flask server"""
        try:
            # Send via LiveKit data channel (existing method)
            if hasattr(self, '_room') and self._room:
                message = json.dumps(data).encode()
                await self._room.local_participant.publish_data(message)
            
            # Also send to Flask server for SSE streaming
            await self.send_to_flask_server(data)
        except Exception as e:
            print(f"Error sending data to frontend: {e}")
    
    async def send_to_flask_server(self, data: dict):
        """Send data to Flask server for SSE streaming"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'http://localhost:5000/api/agent/data',
                    json=data,
                    headers={'Content-Type': 'application/json'}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"Sent data to {result.get('clients_notified', 0)} SSE clients")
                    else:
                        print(f"Failed to send data to Flask server: {response.status}")
        except Exception as e:
            print(f"Error sending data to Flask server: {e}")


async def entrypoint(ctx: agents.JobContext):
    # Create enhanced agent instance
    agent = EnhancedAssistant()
    
    # Store room reference for data communication
    agent._room = ctx.room
    
    session = AgentSession(
        stt=assemblyai.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=rime.TTS(),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    # Listen for data messages from frontend
    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        # Run the async handler
        import asyncio
        asyncio.create_task(agent.on_data_received(data))
    
    # Listen for transcription events to stream conversation
    @session.on("transcript")
    def on_transcript(transcript):
        # Stream transcript to Flask server
        import asyncio
        asyncio.create_task(agent.send_to_flask_server({
            "type": "transcript",
            "text": transcript.text,
            "participant": transcript.participant.identity,
            "timestamp": transcript.timestamp
        }))
    
    # Listen for agent speech events
    @session.on("agent_speech_started")
    def on_agent_speech_started():
        import asyncio
        asyncio.create_task(agent.send_to_flask_server({
            "type": "agent_speech_started",
            "timestamp": time.time()
        }))
    
    @session.on("agent_speech_finished")
    def on_agent_speech_finished():
        import asyncio
        asyncio.create_task(agent.send_to_flask_server({
            "type": "agent_speech_finished", 
            "timestamp": time.time()
        }))

    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            # For telephony applications, use `BVCTelephony` instead
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )

    # Send initial status to frontend
    await agent.send_data_to_frontend({
        "type": "agent_ready",
        "message": "Voice agent is ready and listening"
    })


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
