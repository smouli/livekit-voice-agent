"""Configuration settings for the multi-agent LiveKit voice system."""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

@dataclass
class LiveKitConfig:
    """LiveKit connection configuration."""
    url: str = os.getenv("LIVEKIT_URL", "ws://localhost:7880")
    api_key: str = os.getenv("LIVEKIT_API_KEY", "")
    api_secret: str = os.getenv("LIVEKIT_API_SECRET", "")
    room_name: str = os.getenv("ROOM_NAME", "multi-agent-voice-room")

@dataclass
class OpenAIConfig:
    """OpenAI API configuration for TTS/STT."""
    api_key: str = os.getenv("OPENAI_API_KEY", "")

@dataclass
class AgentConfig:
    """Individual agent configuration."""
    name: str
    identity: str
    accepts_user_input: bool = False
    personality: Optional[str] = None

# Agent configurations for podcast-style conversation
HOST_AGENT = AgentConfig(
    name="PodcastHost",
    identity="podcast-host",
    accepts_user_input=True,
    personality="""I'm a professional podcast host. I guide conversations, ask engaging questions, 
    keep discussions flowing, and welcome listener participation. I'm enthusiastic, articulate, 
    and skilled at managing conversation dynamics. I can seamlessly handle interruptions from 
    listeners and incorporate their questions or comments into the discussion."""
)

GUEST_AGENT = AgentConfig(
    name="PodcastGuest",
    identity="podcast-guest",
    accepts_user_input=True,
    personality="""I'm a knowledgeable podcast guest. I share insights, tell stories, 
    answer questions thoughtfully, and engage naturally with both the host and any listeners 
    who join the conversation. I'm approachable and responsive to audience participation, 
    treating interruptions as opportunities for deeper engagement."""
)

# Global configuration instances
livekit_config = LiveKitConfig()
openai_config = OpenAIConfig()
