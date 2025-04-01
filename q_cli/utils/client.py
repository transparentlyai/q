"""LLM client wrapper for q_cli."""

import os
from typing import Dict, List, Optional, Any, Union
import littlellm

from q_cli.utils.constants import DEFAULT_MODEL, DEBUG


class LLMClient:
    """Unified client wrapper for LLM providers via LittleLLM."""

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
            provider: LLM provider (anthropic, vertex, groq) - optional, can be inferred
        """
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.provider = provider

        # Set up LittleLLM defaults
        if self.api_key:
            # Determine which environment variable to set based on inferred provider
            self._setup_provider_env_vars()
        
        # Map provider/model configurations here
        self.client = littlellm

    def _setup_provider_env_vars(self) -> None:
        """Set up the appropriate environment variables for the provider."""
        # Parse the model string to determine the likely provider if not specified
        if not self.provider:
            if "claude" in self.model.lower():
                self.provider = "anthropic"
            elif "gemini" in self.model.lower() or "vertex" in self.model.lower():
                self.provider = "vertex"
            elif "groq" in self.model.lower():
                self.provider = "groq"
            else:
                # Default fallback
                self.provider = "anthropic"
        
        # Set the environment variable
        if self.provider == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = self.api_key
        elif self.provider == "vertex":
            os.environ["VERTEXAI_API_KEY"] = self.api_key
        elif self.provider == "groq":
            os.environ["GROQ_API_KEY"] = self.api_key

    def messages_create(
        self,
        model: str,
        max_tokens: int,
        temperature: float,
        system: str,
        messages: List[Dict[str, Any]],
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
            **kwargs: Additional arguments to pass to the API

        Returns:
            Response object with similar structure to Anthropic API
        """
        # Transform the messages to the format expected by LittleLLM
        transformed_messages = self._transform_messages(messages, system)
        
        # Make the API call
        try:
            response = self.client.completion(
                model=model,
                messages=transformed_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

            # Convert the response to match the expected format by existing code
            return self._transform_response(response)
        except Exception as e:
            # Modify this to handle specific LittleLLM exceptions as needed
            raise e

    def _transform_messages(
        self, messages: List[Dict[str, Any]], system: str = None
    ) -> List[Dict[str, Any]]:
        """
        Transform messages to the format expected by LittleLLM.

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
            print(f"Transformed messages: {transformed}")
        
        return transformed

    def _transform_response(self, response: Any) -> Any:
        """
        Transform LittleLLM response to match Anthropic API format.

        Args:
            response: The response from LittleLLM

        Returns:
            Transformed response
        """
        # Create an object that mimics the structure expected by the existing code
        class TransformedResponse:
            def __init__(self, llm_response):
                self.usage = None
                if hasattr(llm_response, "usage") and llm_response.usage:
                    class Usage:
                        def __init__(self, usage_data):
                            self.input_tokens = usage_data.get("prompt_tokens", 0)
                            self.output_tokens = usage_data.get("completion_tokens", 0)
                    
                    self.usage = Usage(llm_response.usage)
                
                # Handle content format
                self.content = []
                if hasattr(llm_response, "choices") and llm_response.choices:
                    message = llm_response.choices[0].message
                    content = message.get("content", "")
                    
                    class ContentItem:
                        def __init__(self, text):
                            self.text = text
                            self.type = "text"
                    
                    self.content.append(ContentItem(content))
                
                # Add any other fields that might be needed
                self.stop_reason = getattr(llm_response, "finish_reason", None)
        
        return TransformedResponse(response)