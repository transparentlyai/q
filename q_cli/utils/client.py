"""LLM client wrapper for q_cli using LiteLLM."""

import os
from typing import Dict, List, Optional, Any, Union
import litellm

from q_cli.utils.constants import get_debug, ANTHROPIC_DEFAULT_MODEL
from q_cli.utils.provider_factory import ProviderFactory, BaseProviderConfig


class LLMClient:
    """Unified client wrapper for LLM providers via LiteLLM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize the LLM client.

        Args:
            api_key: API key for the LLM provider
            model: Model name to use
            provider: LLM provider (anthropic, vertexai, groq, openai) - optional, can be inferred
            **kwargs: Additional provider-specific configuration parameters
        """
        # Use the model provided or let the provider factory handle defaults
        self.model = model or ANTHROPIC_DEFAULT_MODEL
        
        # Create provider configuration using factory
        self.provider_config = ProviderFactory.create_provider(
            provider_name=provider,
            model=self.model,
            api_key=api_key,
            **kwargs
        )
        
        # Store provider name for convenience
        self.provider = self.provider_config.get_provider_name()
        
        # Set up environment variables for the provider
        if api_key:
            self.provider_config.setup_environment()
        
        # Format model name according to provider conventions
        self.model = self.provider_config.format_model_name(self.model)
        
        # Initialize litellm
        self.client = litellm

        if get_debug():
            print(f"Initialized LLMClient with provider={self.provider}, model={self.model}")

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
            Response object with OpenAI API-compatible format
        """
        # Transform the messages to the format expected by LiteLLM
        transformed_messages = self._transform_messages(messages, system)
        
        # Ensure max_tokens doesn't exceed the provider's limit
        provider_max_tokens = self.provider_config.MAX_TOKENS
        adjusted_max_tokens = min(max_tokens, provider_max_tokens)
            
        if get_debug() and adjusted_max_tokens != max_tokens:
            print(f"Adjusting max_tokens from {max_tokens} to {adjusted_max_tokens} to respect {self.provider} limits")
        
        # Build request parameters dictionary with only non-None parameters
        request_params = {
            "model": model,
            "messages": transformed_messages,
            "max_tokens": adjusted_max_tokens,
            "temperature": temperature,
            "stream": stream
        }
        
        # Add any additional kwargs
        request_params.update(kwargs)
        
        try:
            # Make the API call
            if get_debug():
                print(f"LiteLLM request: provider={self.provider}, model={model}, max_tokens={request_params['max_tokens']}, stream={stream}")
                print(f"Using provider config: {self.provider_config.get_config()}")
                
            response = self.client.completion(**request_params)

            # Convert the response to match the expected format by existing code
            return self._transform_response(response, stream=stream)
            
        except litellm.exceptions.BadRequestError as e:
            if get_debug():
                print(f"LiteLLM bad request error: {str(e)}")
            
            # Use provider-specific error handling
            error_handlers = self.provider_config.get_error_handler()
            for error_key, handler in error_handlers.items():
                if error_key in str(e):
                    error_msg = f"{handler['message']}\n\nOriginal error: {str(e)}"
                    raise Exception(error_msg)
                    
            # If no specific handler, re-raise the original exception
            raise e
            
        except litellm.exceptions.RateLimitError as e:
            if get_debug():
                print(f"LiteLLM rate limit error: {str(e)}")
            raise e
            
        except litellm.exceptions.AuthenticationError as e:
            if get_debug():
                print(f"LiteLLM authentication error: {str(e)}")
            
            # Use provider-specific error handling
            error_handlers = self.provider_config.get_error_handler()
            for error_key, handler in error_handlers.items():
                if error_key in str(e):
                    error_msg = f"{handler['message']}\n\nOriginal error: {str(e)}"
                    raise Exception(error_msg)
                    
            # Default authentication error message
            error_msg = f"Authentication error with {self.provider}. Please check your API key and credentials."
            raise Exception(f"{error_msg}\n\nOriginal error: {str(e)}")
            
        except litellm.exceptions.APIError as e:
            if get_debug():
                print(f"LiteLLM API error: {str(e)}")
            raise e
            
        except litellm.exceptions.ServiceUnavailableError as e:
            if get_debug():
                print(f"LiteLLM service unavailable error: {str(e)}")
            raise e
            
        # Generic exception handler for all other cases including ContentFilterError
        except Exception as e:
            if get_debug():
                print(f"LiteLLM error: {str(e)}")
            
            # Check if this might be a content filter error based on the error message
            error_str = str(e).lower()
            if any(term in error_str for term in ['content filter', 'content_filter', 'contentfilter']):
                if get_debug():
                    print(f"Content filter triggered: {str(e)}")
                raise Exception(f"Content filter triggered: {str(e)}")
            
            # Use provider-specific error handling for generic errors too
            error_handlers = self.provider_config.get_error_handler()
            for error_key, handler in error_handlers.items():
                if error_key in str(e):
                    error_msg = f"{handler['message']}\n\nOriginal error: {str(e)}"
                    raise Exception(error_msg)
            
            # Re-raise the original exception if not handled specifically
            raise e

    def _transform_messages(
        self, messages: List[Dict[str, Any]], system: str = None
    ) -> List[Dict[str, Any]]:
        """
        Transform messages to the format expected by LiteLLM.

        Args:
            messages: Original messages from q_cli format
            system: System prompt

        Returns:
            Transformed messages in format expected by LiteLLM
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
        
        if get_debug():
            print(f"Transformed {len(messages)} messages for LiteLLM")
        
        return transformed

    def _transform_response(self, response: Any, stream: bool = False) -> Any:
        """
        Transform LiteLLM response to match OpenAI API format.

        Args:
            response: The response from LiteLLM
            stream: Whether the response is streaming

        Returns:
            Transformed response with OpenAI-compatible structure
        """
        if stream:
            # For streaming, return a generator that transforms each chunk
            return self._transform_streaming_response(response)
        
        # Create an object that mimics the structure expected by the existing code
        class TransformedResponse:
            def __init__(self, llm_response):
                # Basic response metadata
                self.id = getattr(llm_response, "id", "chatcmpl-" + str(hash(str(llm_response)))[:8])
                self.created = getattr(llm_response, "created", 0)
                self.model = getattr(llm_response, "model", "")
                self.object = "chat.completion"
                self.system_fingerprint = getattr(llm_response, "system_fingerprint", None)
                self.response_ms = getattr(llm_response, "response_ms", 0)
                
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
                        # Process message content and tool calls
                        message_content = ""
                        message_tool_calls = None
                        message_function_call = None
                        
                        if hasattr(choice, "message"):
                            msg = choice.message
                            if isinstance(msg, dict):
                                message_content = msg.get("content", "")
                                
                                # Extract tool calls and function calls if present
                                if "tool_calls" in msg:
                                    message_tool_calls = msg.get("tool_calls")
                                if "function_call" in msg:
                                    message_function_call = msg.get("function_call")
                            else:
                                # If message is an object with attributes
                                message_content = getattr(msg, "content", "")
                                message_tool_calls = getattr(msg, "tool_calls", None)
                                message_function_call = getattr(msg, "function_call", None)
                        
                        # Create message object
                        message = {
                            "content": message_content,
                            "role": "assistant",
                            "tool_calls": message_tool_calls,
                            "function_call": message_function_call
                        }
                        
                        # Get finish_reason, handling different formats
                        finish_reason = None
                        if hasattr(choice, "finish_reason"):
                            finish_reason = choice.finish_reason
                        elif isinstance(choice, dict) and "finish_reason" in choice:
                            finish_reason = choice["finish_reason"]
                        
                        # Create choice object
                        choice_obj = {
                            "finish_reason": finish_reason or "stop",
                            "index": i,
                            "message": message,
                            "logprobs": getattr(choice, "logprobs", None)
                        }
                        
                        self.choices.append(choice_obj)
                        
                        # For backward compatibility with code expecting content
                        class ContentItem:
                            def __init__(self, text):
                                self.text = text
                                self.type = "text"
                        
                        self.content.append(ContentItem(message_content))
                
                # Dictionary-style and attribute-style access
                def __getitem__(self, key):
                    return getattr(self, key)
                
                def to_dict(self):
                    """Convert to dict for debugging."""
                    return {
                        "id": self.id,
                        "created": self.created,
                        "model": self.model,
                        "object": self.object,
                        "system_fingerprint": self.system_fingerprint,
                        "choices": self.choices,
                        "usage": self.usage.__dict__ if self.usage else None
                    }
                
                def __str__(self):
                    # Lazy import json only when needed
                    import json
                    return json.dumps(self.to_dict(), indent=2)
        
        return TransformedResponse(response)
    
    def _transform_streaming_response(self, streaming_response):
        """
        Transform a streaming response from LiteLLM to match OpenAI API format.
        
        Args:
            streaming_response: The streaming response from LiteLLM
            
        Returns:
            Generator that yields transformed response chunks with OpenAI-compatible structure
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
                            # Extract delta content and other elements
                            content = ""
                            function_call = None
                            tool_calls = None
                            
                            # Handle different possible delta formats
                            if hasattr(choice, "delta"):
                                delta_obj = choice.delta
                                if hasattr(delta_obj, "content"):
                                    content = delta_obj.content
                                elif isinstance(delta_obj, dict) and "content" in delta_obj:
                                    content = delta_obj["content"]
                                
                                # Extract function call if present
                                if hasattr(delta_obj, "function_call"):
                                    function_call = delta_obj.function_call
                                elif isinstance(delta_obj, dict) and "function_call" in delta_obj:
                                    function_call = delta_obj["function_call"]
                                
                                # Extract tool calls if present
                                if hasattr(delta_obj, "tool_calls"):
                                    tool_calls = delta_obj.tool_calls
                                elif isinstance(delta_obj, dict) and "tool_calls" in delta_obj:
                                    tool_calls = delta_obj["tool_calls"]
                            
                            # Create delta object
                            delta = {
                                "content": content,
                                "role": "assistant",
                                "function_call": function_call,
                                "tool_calls": tool_calls,
                                "audio": None
                            }
                            
                            # Get finish_reason, handling different formats
                            finish_reason = None
                            if hasattr(choice, "finish_reason"):
                                finish_reason = choice.finish_reason
                            elif isinstance(choice, dict) and "finish_reason" in choice:
                                finish_reason = choice["finish_reason"]
                            
                            # Create choice object
                            choice_obj = {
                                "finish_reason": finish_reason,
                                "index": i,
                                "delta": delta,
                                "logprobs": getattr(choice, "logprobs", None)
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
                            
                    # Dictionary-style access
                    def __getitem__(self, key):
                        return getattr(self, key)
                    
                    def to_dict(self):
                        """Convert to dict for debugging."""
                        return {
                            "id": self.id,
                            "created": self.created,
                            "model": self.model,
                            "object": self.object,
                            "system_fingerprint": self.system_fingerprint,
                            "choices": self.choices
                        }
                    
                    def __str__(self):
                        # Lazy import json only when needed
                        import json
                        return json.dumps(self.to_dict(), indent=2)
            
            yield TransformedChunk(chunk)