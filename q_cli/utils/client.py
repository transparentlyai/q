"""LLM client wrapper for q_cli using LiteLLM."""

import os
from typing import Dict, List, Optional, Any, Union
import litellm
import json

from q_cli.utils.constants import DEFAULT_MODEL, DEBUG


class LLMClient:
    """Unified client wrapper for LLM providers via LiteLLM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        """
        Initialize the LLM client.

        Args:
            api_key: API key for the LLM provider
            model: Model name to use
            provider: LLM provider (anthropic, vertexai, groq) - optional, can be inferred
        """
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.provider = provider
        
        # Determine provider from model if not specified
        if not self.provider:
            if "claude" in self.model.lower():
                self.provider = "anthropic"
            elif "gemini" in self.model.lower():
                self.provider = "vertexai"
            elif "deepseek" in self.model.lower() or "llama" in self.model.lower() or "mixtral" in self.model.lower():
                self.provider = "groq"
            else:
                # Default fallback
                self.provider = "anthropic"

        # Set up LiteLLM API keys
        if self.api_key:
            self._setup_provider_env_vars()
        
        # Initialize litellm
        self.client = litellm

        if DEBUG:
            print(f"Initialized LLMClient with provider={self.provider}, model={self.model}")

    def _setup_provider_env_vars(self) -> None:
        """Set up the appropriate environment variables for the provider."""
        # Set provider-specific API keys
        if self.provider.lower() == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = self.api_key
        elif self.provider.lower() == "vertexai":
            # VertexAI typically uses service account credentials
            # For simplicity we'll set an environment variable that our code uses
            os.environ["VERTEXAI_API_KEY"] = self.api_key
            # These are typically required for VertexAI
            if "VERTEXAI_PROJECT" not in os.environ and "VERTEX_PROJECT" not in os.environ:
                if DEBUG:
                    print("WARNING: VERTEXAI_PROJECT not set in environment")
        elif self.provider.lower() == "groq":
            os.environ["GROQ_API_KEY"] = self.api_key
        elif self.provider.lower() == "openai":
            os.environ["OPENAI_API_KEY"] = self.api_key
        
        # Set default model prefix based on provider if not already in model name
        if not "/" in self.model:
            if self.provider.lower() == "anthropic":
                self.model = f"anthropic/{self.model}"
            elif self.provider.lower() == "vertexai":
                self.model = f"vertex_ai/{self.model}"
            elif self.provider.lower() == "groq":
                self.model = f"groq/{self.model}"
            elif self.provider.lower() == "openai":
                self.model = f"openai/{self.model}"

    def messages_create(
        self,
        model: str,
        max_tokens: int,
        temperature: float,
        system: str,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        **kwargs
    ) -> Any:
        """
        Create a new chat completion with messages.

        Args:
            model: The model to use
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature
            system: System prompt
            messages: List of messages to send to the model
            stream: Whether to stream the response
            **kwargs: Additional arguments to pass to the API

        Returns:
            Response object with similar structure to Anthropic API
        """
        # Transform the messages to the format expected by LittleLLM
        transformed_messages = self._transform_messages(messages, system)
        
        try:
            # Make the API call
            if DEBUG:
                print(f"LittleLLM request: model={model}, max_tokens={max_tokens}, stream={stream}")
                
            response = self.client.completion(
                model=model,
                messages=transformed_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=stream,
                **kwargs
            )

            # Convert the response to match the expected format by existing code
            return self._transform_response(response, stream=stream)
            
        except Exception as e:
            if DEBUG:
                print(f"LiteLLM error: {str(e)}")
            # Let the caller handle the exception with its error mapping
            raise e

    def _transform_messages(
        self, messages: List[Dict[str, Any]], system: str = None
    ) -> List[Dict[str, Any]]:
        """
        Transform messages to the format expected by LiteLLM.

        Args:
            messages: Original messages in Anthropic format
            system: System prompt

        Returns:
            Transformed messages
        """
        transformed = []
        
        # Add system message if provided
        if system:
            transformed.append({"role": "system", "content": system})
        
        # Process each message based on its role and content
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # Handle multimodal content
            if isinstance(content, list):
                # Filter out and convert image data if present
                text_parts = []
                image_parts = []
                
                for item in content:
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "image":
                        # Extract image data
                        image_data = item.get("source", {}).get("data", "")
                        mime_type = item.get("source", {}).get("media_type", "image/jpeg")
                        
                        if image_data:
                            image_parts.append({
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_data}",
                                }
                            })
                
                # Combine text parts
                combined_text = " ".join(text_parts)
                
                # If we have both text and images
                if text_parts and image_parts:
                    transformed.append({
                        "role": role,
                        "content": [{"type": "text", "text": combined_text}] + image_parts
                    })
                # If we have only text
                elif text_parts:
                    transformed.append({"role": role, "content": combined_text})
                # If we have only images
                elif image_parts:
                    transformed.append({"role": role, "content": image_parts})
            else:
                # Simple text message
                transformed.append({"role": role, "content": content})
        
        if DEBUG:
            print(f"Transformed {len(messages)} messages for LiteLLM")
        
        return transformed

    def _transform_response(self, response: Any, stream: bool = False) -> Any:
        """
        Transform LiteLLM response to match Anthropic API format.

        Args:
            response: The response from LiteLLM
            stream: Whether the response is streaming

        Returns:
            Transformed response
        """
        if stream:
            # For streaming, return a generator that transforms each chunk
            return self._transform_streaming_response(response)
        
        # Create an object that mimics the structure expected by the existing code
        class TransformedResponse:
            def __init__(self, llm_response):
                self.id = getattr(llm_response, "id", "chatcmpl-" + str(hash(str(llm_response)))[:8])
                self.created = getattr(llm_response, "created", 0)
                self.model = getattr(llm_response, "model", "")
                self.object = "chat.completion"
                self.system_fingerprint = None
                
                # Handle usage information
                self.usage = None
                if hasattr(llm_response, "usage") and llm_response.usage:
                    class Usage:
                        def __init__(self, usage_data):
                            if isinstance(usage_data, dict):
                                self.input_tokens = usage_data.get("prompt_tokens", 0)
                                self.output_tokens = usage_data.get("completion_tokens", 0)
                                self.total_tokens = usage_data.get("total_tokens", 0)
                            else:
                                self.input_tokens = getattr(usage_data, "prompt_tokens", 0)
                                self.output_tokens = getattr(usage_data, "completion_tokens", 0)
                                self.total_tokens = getattr(usage_data, "total_tokens", 0)
                    
                    self.usage = Usage(llm_response.usage)
                
                # Handle content format
                self.content = []
                self.choices = []
                
                if hasattr(llm_response, "choices") and llm_response.choices:
                    for i, choice in enumerate(llm_response.choices):
                        # Process message content
                        message_content = ""
                        if hasattr(choice, "message"):
                            message_content = choice.message.get("content", "")
                        elif hasattr(choice, "delta") and hasattr(choice.delta, "content"):
                            message_content = choice.delta.content
                        
                        # Create message object
                        message = {
                            "content": message_content,
                            "role": "assistant",
                            "tool_calls": None,
                            "function_call": None
                        }
                        
                        # Create choice object
                        choice_obj = {
                            "finish_reason": getattr(choice, "finish_reason", "stop"),
                            "index": i,
                            "message": message
                        }
                        
                        self.choices.append(choice_obj)
                        
                        # For backward compatibility with code expecting content
                        class ContentItem:
                            def __init__(self, text):
                                self.text = text
                                self.type = "text"
                        
                        self.content.append(ContentItem(message_content))
                
                # Add any other fields that might be needed
                self.stop_reason = getattr(llm_response, "finish_reason", None)
                
                def to_dict(self):
                    """Convert to dict for debugging."""
                    return {
                        "id": self.id,
                        "created": self.created,
                        "model": self.model,
                        "object": self.object,
                        "choices": self.choices,
                    }
                
                def __str__(self):
                    return json.dumps(self.to_dict(), indent=2)
        
        return TransformedResponse(response)
    
    def _transform_streaming_response(self, streaming_response):
        """
        Transform a streaming response from LiteLLM to match Anthropic's streaming format.
        
        Args:
            streaming_response: The streaming response from LiteLLM
            
        Returns:
            Generator that yields transformed response chunks
        """
        for chunk in streaming_response:
            # Create a class to mimic the structure expected by the existing code
            class TransformedChunk:
                def __init__(self, chunk):
                    self.id = getattr(chunk, "id", "chatcmpl-" + str(hash(str(chunk)))[:8])
                    self.created = getattr(chunk, "created", 0)
                    self.model = getattr(chunk, "model", "")
                    self.object = "chat.completion.chunk"
                    self.system_fingerprint = None
                    
                    # Handle content format
                    self.choices = []
                    if hasattr(chunk, "choices") and chunk.choices:
                        for i, choice in enumerate(chunk.choices):
                            # Extract delta content
                            content = ""
                            
                            # Handle different possible delta formats
                            if hasattr(choice, "delta"):
                                if hasattr(choice.delta, "content"):
                                    content = choice.delta.content
                                elif isinstance(choice.delta, dict) and "content" in choice.delta:
                                    content = choice.delta["content"]
                            
                            # Create delta object
                            delta = {
                                "content": content,
                                "role": "assistant",
                                "function_call": None,
                                "tool_calls": None,
                                "audio": None
                            }
                            
                            # Create choice object
                            choice_obj = {
                                "finish_reason": getattr(choice, "finish_reason", None),
                                "index": i,
                                "delta": delta,
                                "logprobs": None
                            }
                            
                            self.choices.append(choice_obj)
                    
                    # Add content array for compatibility
                    self.content = []
                    if self.choices and "content" in self.choices[0].get("delta", {}):
                        class ContentItem:
                            def __init__(self, text):
                                self.text = text
                                self.type = "text"
                        
                        content_text = self.choices[0]["delta"]["content"]
                        if content_text:
                            self.content.append(ContentItem(content_text))
            
            yield TransformedChunk(chunk)