from fastapi import FastAPI, Request, HTTPException
from langchain_ollama.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- Model Configuration ---
# Point to the model running in your local Ollama service
MODEL_NAME = "qwen2.5-coder:7b"

app = FastAPI(title="Ollama-based LLM Inference API")

# Instantiate the ChatOllama model
# This assumes Ollama is running at its default location (http://localhost:11434)
try:
    llm = ChatOllama(model=MODEL_NAME)
    print(f"Successfully connected to Ollama model: {MODEL_NAME}")
except Exception as e:
    print(f"Failed to connect to Ollama. Please ensure Ollama is running. Error: {e}")
    llm = None

@app.post("/generate")
async def generate(request: Request):
    """
    Accepts a prompt and returns the model's generated text using Ollama.
    Expects a JSON payload with a "prompt" key.
    """
    if llm is None:
        raise HTTPException(status_code=503, detail="Ollama model is not available. Please check the logs.")

    try:
        data = await request.json()
        prompt_text = data.get("prompt")
        if not prompt_text:
            raise HTTPException(status_code=400, detail="'prompt' field is missing from request.")
            
        print(f"Generating response for prompt (first 80 chars): {prompt_text[:80]}...")
        
        # Using a simple prompt template
        prompt = ChatPromptTemplate.from_template("{user_prompt}")
        
        # Create a simple chain
        chain = prompt | llm | StrOutputParser()
        
        # Invoke the chain to get the response
        generated_text = await chain.ainvoke({"user_prompt": prompt_text})
        
        print("Text generation complete.")
        
        return {"output": generated_text}
        
    except Exception as e:
        print(f"An error occurred during text generation: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred during generation: {e}")

@app.get("/health")
def health_check():
    """
    Health check endpoint. Confirms the service is running and the Ollama model is configured.
    """
    model_status = "configured" if llm is not None else "not configured"
    return {"status": "ok", "ollama_model_status": model_status}

if __name__ == "__main__":
    import uvicorn
    print("Starting Ollama-based LLM Inference Service...")
    print("This service connects to your local Ollama instance.")
    print("Navigate to http://localhost:8001/docs for API documentation.")
    uvicorn.run(app, host="0.0.0.0", port=8001)
