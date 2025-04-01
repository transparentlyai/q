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
            provider: LLM provider (anthropic, vertexai, groq, openai) - optional, can be inferred
        """
        self.api_key = api_key
        self.model = model or DEFAULT_MODEL
        self.provider = provider
        
        # Determine provider from model if not specified
        if not self.provider:
            model_lower = self.model.lower()
            
            # Anthropic models
            if "claude" in model_lower:
                self.provider = "anthropic"
                
            # VertexAI/Google models
            elif any(name in model_lower for name in ["gemini", "gecko", "gemma", "palm"]):
                self.provider = "vertexai"
                
            # Groq models (mostly hosted versions of open models)
            elif any(name in model_lower for name in ["deepseek", "llama", "mixtral", "falcon"]):
                self.provider = "groq"
                
            # OpenAI models
            elif any(name in model_lower for name in ["gpt", "ft:gpt", "text-davinci", "dall-e"]):
                self.provider = "openai"
                
            # Check for provider prefixes in model name
            elif "google/" in model_lower or "vertex" in model_lower:
                self.provider = "vertexai"
            elif "anthropic/" in model_lower:
                self.provider = "anthropic"
            elif "groq/" in model_lower:
                self.provider = "groq"
            elif "openai/" in model_lower:
                self.provider = "openai"
                
            else:
                # Default fallback to provider from constants
                from q_cli.utils.constants import DEFAULT_PROVIDER
                self.provider = DEFAULT_PROVIDER
                
            if DEBUG:
                print(f"Inferred provider '{self.provider}' from model name '{self.model}'")
                
        # Normalize provider name to lowercase
        self.provider = self.provider.lower()

        # Set up LiteLLM API keys
        if self.api_key:
            self._setup_provider_env_vars()
        
        # Initialize litellm
        self.client = litellm

        if DEBUG:
            print(f"Initialized LLMClient with provider={self.provider}, model={self.model}")

    def _has_content_filter_error(self) -> bool:
        """Check if litellm has ContentFilterError class available."""
        try:
            # First check if the attribute exists
            if hasattr(litellm.exceptions, 'ContentFilterError'):
                return True
                
            # If the attribute doesn't exist directly, let's check if any exception
            # class in litellm.exceptions has "ContentFilter" in its name
            for attr_name in dir(litellm.exceptions):
                if 'contentfilter' in attr_name.lower() or 'content_filter' in attr_name.lower():
                    return True
                    
            return False
        except:
            return False
            
    def _setup_provider_env_vars(self) -> None:
        """Set up the appropriate environment variables for the provider."""
        # Set provider-specific API keys
        if self.provider.lower() == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = self.api_key
        elif self.provider.lower() == "vertexai":
            # VertexAI typically uses service account credentials in a JSON file
            if self.api_key is not None:
                if os.path.isfile(self.api_key):
                    # If api_key is a path to a file, set GOOGLE_APPLICATION_CREDENTIALS
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.api_key
                    
                    # Convert to absolute path if not already
                    if not os.path.isabs(self.api_key):
                        abs_path = os.path.abspath(self.api_key)
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
                        
                    if DEBUG:
                        print(f"Set GOOGLE_APPLICATION_CREDENTIALS to {os.environ['GOOGLE_APPLICATION_CREDENTIALS']}")
                        # Check if the file exists and has proper permissions
                        try:
                            with open(os.environ["GOOGLE_APPLICATION_CREDENTIALS"], 'r') as f:
                                content = f.read(100)  # Read just a bit to verify access
                                if content.strip().startswith('{'):
                                    print(f"Successfully opened credentials file and confirmed JSON format")
                                    
                                    # Optionally, try to extract the project ID from the credentials file
                                    try:
                                        import json
                                        full_content = f.seek(0) and f.read()
                                        creds_json = json.loads(full_content)
                                        if 'project_id' in creds_json and not os.environ.get("VERTEXAI_PROJECT"):
                                            os.environ["VERTEXAI_PROJECT"] = creds_json['project_id']
                                            print(f"Extracted project_id from credentials: {creds_json['project_id']}")
                                    except Exception as e:
                                        if DEBUG:
                                            print(f"Could not extract project_id from credentials: {str(e)}")
                                else:
                                    print(f"WARNING: Credentials file does not appear to be valid JSON")
                        except Exception as e:
                            print(f"WARNING: Error accessing credentials file: {str(e)}")
                else:
                    # Fallback to using as a direct key (though this is not standard for VertexAI)
                    print(f"WARNING: API key '{self.api_key}' is not a file path. VertexAI typically expects a JSON service account file.")
                    os.environ["VERTEXAI_API_KEY"] = self.api_key
                    if DEBUG:
                        print(f"Using direct API key for VertexAI (not recommended)")
            else:
                if DEBUG:
                    print("WARNING: No API key provided for VertexAI")
                
            # Check for project ID which is required for VertexAI
            project_id = None
            
            # Try to get project ID from various environment variables
            for env_var in ["VERTEXAI_PROJECT", "VERTEX_PROJECT", "GOOGLE_PROJECT", "PROJECT_ID", "GCP_PROJECT"]:
                if env_var in os.environ and os.environ[env_var].strip():
                    project_id = os.environ[env_var].strip()
                    if DEBUG:
                        print(f"Found project ID in {env_var}: {project_id}")
                    break
            
            # Try to extract from credentials file if not found in environment
            if not project_id and self.api_key and os.path.isfile(self.api_key):
                try:
                    import json
                    with open(self.api_key, 'r') as f:
                        creds_data = json.load(f)
                        if 'project_id' in creds_data:
                            project_id = creds_data['project_id']
                            if DEBUG:
                                print(f"Extracted project_id from credentials file: {project_id}")
                except Exception as e:
                    if DEBUG:
                        print(f"Error extracting project_id from credentials file: {str(e)}")
            
            # Try to extract from the filename if it's of form "project-name-123456.json"
            if not project_id and self.api_key and os.path.isfile(self.api_key):
                try:
                    filename = os.path.basename(self.api_key)
                    if "-" in filename and (filename.endswith(".json") or filename.endswith(".JSON")):
                        # Try to extract project ID from filename (common pattern for GCP service accounts)
                        possible_project = filename.split(".json")[0].split(".JSON")[0]
                        if DEBUG:
                            print(f"Possible project ID from filename: {possible_project}")
                        project_id = possible_project
                except Exception as e:
                    if DEBUG:
                        print(f"Error extracting project_id from filename: {str(e)}")
            
            # If celeritas-eng-dev is in the service account path, use it (specific to your setup)
            if not project_id and self.api_key and "celeritas-eng-dev" in self.api_key:
                project_id = "celeritas-eng-dev"
                if DEBUG:
                    print(f"Using project ID from path: {project_id}")
                    
            # Special case for q-for-mauro.json
            if not project_id and self.api_key and "q-for-mauro.json" in str(self.api_key):
                project_id = "celeritas-eng-dev"
                if DEBUG:
                    print(f"Using hardcoded project ID for q-for-mauro.json: {project_id}")
            
            # Set the project ID in all expected environment variables if we found it
            if project_id:
                for env_var in ["GOOGLE_PROJECT", "VERTEXAI_PROJECT", "PROJECT_ID", "GCP_PROJECT"]:
                    os.environ[env_var] = project_id
                if DEBUG:
                    print(f"Set all project environment variables to: {project_id}")
            else:
                print("ERROR: VERTEXAI_PROJECT not set in environment (required for VertexAI)")
                print("Please set VERTEXAI_PROJECT in your config file or environment variables")
                
                # Print debug info to help diagnose the issue
                if DEBUG:
                    print(f"API key: {self.api_key}")
                    print(f"Current environment variables:")
                    for key in sorted(os.environ.keys()):
                        if "PROJECT" in key or "VERTEX" in key or "GOOGLE" in key:
                            print(f"  {key}={os.environ[key]}")
                    print("Config file settings should be in ~/.config/q.conf")
                
            # Set location for VertexAI (required by litellm)
            location = None
            
            # First try to find it in any of the possible environment variables
            for env_var in ["VERTEXAI_LOCATION", "VERTEX_LOCATION", "GOOGLE_LOCATION", "LOCATION_ID", "GCP_LOCATION"]:
                if env_var in os.environ and os.environ[env_var].strip():
                    location = os.environ[env_var].strip()
                    if DEBUG:
                        print(f"Found location in {env_var}: {location}")
                    break
                    
            # If we still don't have a location, default to us-west4
            if not location:
                location = "us-west4"  # Your preferred region
                print(f"WARNING: VERTEXAI_LOCATION not set in environment. Defaulting to '{location}'")
                
            # Set the location in all environment variables
            for env_var in ["VERTEX_LOCATION", "VERTEXAI_LOCATION", "LOCATION_ID", "GCP_LOCATION", "GOOGLE_LOCATION"]:
                os.environ[env_var] = location
                
            if DEBUG:
                print(f"Set all location environment variables to: {location}")
                
            # Add additional required environment variables for compatibility with litellm
            if "GOOGLE_PROJECT" in os.environ:
                # Set alternate versions of the project variable that might be used by litellm
                os.environ["PROJECT_ID"] = os.environ["GOOGLE_PROJECT"]
                os.environ["GCP_PROJECT"] = os.environ["GOOGLE_PROJECT"]
                
            if "VERTEX_LOCATION" in os.environ:
                # Set alternate versions of the location variable that might be used by litellm
                os.environ["LOCATION_ID"] = os.environ["VERTEX_LOCATION"]
                os.environ["GCP_LOCATION"] = os.environ["VERTEX_LOCATION"]
                os.environ["GOOGLE_LOCATION"] = os.environ["VERTEX_LOCATION"]
        elif self.provider.lower() == "groq":
            os.environ["GROQ_API_KEY"] = self.api_key
        elif self.provider.lower() == "openai":
            os.environ["OPENAI_API_KEY"] = self.api_key
        
        # Set default model prefix based on provider if not already in model name
        if not "/" in self.model and not ":" in self.model:
            if self.provider.lower() == "anthropic":
                self.model = f"anthropic/{self.model}"
            elif self.provider.lower() == "vertexai":
                # For VertexAI, we need to use google/provider format
                self.model = f"google/{self.model}"
            elif self.provider.lower() == "groq":
                self.model = f"groq/{self.model}"
            elif self.provider.lower() == "openai":
                self.model = f"openai/{self.model}"
                
            if DEBUG:
                print(f"Model name with provider prefix: {self.model}")

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
        
        # Build request parameters dictionary with only non-None parameters
        request_params = {
            "model": model,
            "messages": transformed_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream
        }
        
        # Add any additional kwargs
        request_params.update(kwargs)
        
        try:
            # Make the API call
            if DEBUG:
                print(f"LiteLLM request: model={model}, max_tokens={max_tokens}, stream={stream}")
                
            response = self.client.completion(**request_params)

            # Convert the response to match the expected format by existing code
            return self._transform_response(response, stream=stream)
            
        except litellm.exceptions.BadRequestError as e:
            if DEBUG:
                print(f"LiteLLM bad request error: {str(e)}")
            # Enhance specific provider error messages for better troubleshooting
            if self.provider == "vertexai" and "PERMISSION_DENIED" in str(e):
                error_msg = (
                    f"VertexAI permission denied error. This typically means:\n"
                    f"1. The service account in '{self.api_key}' doesn't have sufficient permissions\n"
                    f"2. Required IAM role: 'roles/aiplatform.user' or 'aiplatform.admin'\n" 
                    f"3. Make sure the Vertex AI API is enabled in project: '{os.environ.get('GOOGLE_PROJECT')}'\n\n"
                    f"Original error: {str(e)}"
                )
                # Use Exception instead of litellm.exceptions.BadRequestError since it requires additional parameters
                raise Exception(error_msg)
            raise e
        except litellm.exceptions.RateLimitError as e:
            if DEBUG:
                print(f"LiteLLM rate limit error: {str(e)}")
            raise e
        except litellm.exceptions.AuthenticationError as e:
            if DEBUG:
                print(f"LiteLLM authentication error: {str(e)}")
            # Enhance auth error messages
            if self.provider == "vertexai":
                error_msg = (
                    f"VertexAI authentication error. Please check:\n"
                    f"1. Your service account JSON file is valid: '{self.api_key}'\n"
                    f"2. Project ID is correct: '{os.environ.get('GOOGLE_PROJECT')}'\n"
                    f"3. Location is correct: '{os.environ.get('VERTEX_LOCATION')}'\n\n"
                    f"Original error: {str(e)}"
                )
                # Use Exception instead of litellm.exceptions.AuthenticationError since it requires additional parameters
                raise Exception(error_msg)
            raise e
        except litellm.exceptions.APIError as e:
            if DEBUG:
                print(f"LiteLLM API error: {str(e)}")
            raise e
        except litellm.exceptions.ServiceUnavailableError as e:
            if DEBUG:
                print(f"LiteLLM service unavailable error: {str(e)}")
            raise e
            
        # Generic exception handler for all other cases including ContentFilterError
        except Exception as e:
            if DEBUG:
                print(f"LiteLLM error: {str(e)}")
            
            # Check if this might be a content filter error based on the error message
            error_str = str(e).lower()
            if 'content filter' in error_str or 'content_filter' in error_str or 'contentfilter' in error_str:
                if DEBUG:
                    print(f"Content filter triggered: {str(e)}")
                raise Exception(f"Content filter triggered: {str(e)}")
                
            # Alternative check using our helper method - this is a more complex approach
            # that tries to use the actual litellm exception type if it exists
            if self._has_content_filter_error():
                try:
                    # Get the ContentFilterError class by name
                    content_filter_class = None
                    for attr_name in dir(litellm.exceptions):
                        if 'contentfilter' in attr_name.lower() or 'content_filter' in attr_name.lower():
                            content_filter_class = getattr(litellm.exceptions, attr_name)
                            break
                            
                    # If we found a ContentFilterError class, check if e is an instance of it
                    if content_filter_class and isinstance(e, content_filter_class):
                        if DEBUG:
                            print(f"Content filter triggered via class check: {str(e)}")
                        raise Exception(f"Content filter triggered: {str(e)}")
                except:
                    # If any part of this fails, we'll continue to the next checks
                    pass
                
            # Check for various types of VertexAI errors
            if self.provider.lower() == "vertexai":
                error_str = str(e)
                
                # Permission error
                if "Permission" in error_str and "denied" in error_str:
                    error_msg = (
                        f"VertexAI access denied error. Please check:\n"
                        f"1. Your service account has 'aiplatform.endpoints.predict' permission\n"
                        f"2. Required IAM role: 'roles/aiplatform.user' or 'aiplatform.admin'\n" 
                        f"3. The model '{model}' is available in your project and region\n" 
                        f"4. Project: '{os.environ.get('GOOGLE_PROJECT')}', Location: '{os.environ.get('VERTEX_LOCATION')}'\n\n"
                        f"Original error: {error_str}"
                    )
                    raise Exception(error_msg)
                
                # Authentication error
                elif any(term in error_str.lower() for term in ["authentication", "unauthenticated", "credentials", "unauthorized", "auth"]):
                    error_msg = (
                        f"VertexAI authentication error. Please check:\n"
                        f"1. Your service account JSON file is valid: '{self.api_key}'\n"
                        f"2. Project ID is correct: '{os.environ.get('GOOGLE_PROJECT')}'\n"
                        f"3. Location is correct: '{os.environ.get('VERTEX_LOCATION')}'\n"
                        f"4. Service account has the necessary permissions\n\n"
                        f"Original error: {error_str}"
                    )
                    raise Exception(error_msg)
                
                # Model not found error
                elif any(term in error_str.lower() for term in ["not found", "notfound", "model", "does not exist"]):
                    gemini_models = ["gemini-1.0-pro", "gemini-1.0-pro-vision", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash-001", "gemini-2.0-pro-001"]
                    model_suggestion = next((m for m in gemini_models if m.split("-")[0] in model.lower()), "gemini-2.0-flash-001")
                    
                    error_msg = (
                        f"VertexAI model error: '{model}' may not exist or isn't accessible. Please check:\n"
                        f"1. The model name is correct (try '{model_suggestion}')\n"
                        f"2. The model is available in your project's region: '{os.environ.get('VERTEX_LOCATION')}'\n"
                        f"3. Your service account has access to this model\n\n"
                        f"Original error: {error_str}"
                    )
                    raise Exception(error_msg)
                
                # Quota exceeded error
                elif any(term in error_str.lower() for term in ["quota", "limit", "exceed", "rate limit"]):
                    error_msg = (
                        f"VertexAI quota exceeded. Please check:\n"
                        f"1. Your project has sufficient quota for VertexAI API calls\n"
                        f"2. Try again after a brief waiting period\n"
                        f"3. Consider requesting higher quotas in Google Cloud Console\n\n"
                        f"Original error: {error_str}"
                    )
                    raise Exception(error_msg)
                
                # Generic VertexAI error with helpful context
                else:
                    error_msg = (
                        f"VertexAI error occurred. Please check:\n"
                        f"1. Project: '{os.environ.get('GOOGLE_PROJECT')}'\n"
                        f"2. Location: '{os.environ.get('VERTEX_LOCATION')}'\n"
                        f"3. Model: '{model}'\n"
                        f"4. Environment variables set: GOOGLE_APPLICATION_CREDENTIALS, VERTEXAI_PROJECT, VERTEXAI_LOCATION\n\n"
                        f"Original error: {error_str}"
                    )
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
        
        if DEBUG:
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
                        return json.dumps(self.to_dict(), indent=2)
            
            yield TransformedChunk(chunk)