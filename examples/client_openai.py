"""
Exemple: Client OpenAI pointant vers le proxy local.

Usage:
    pip install openai
    python examples/client_openai.py
"""
from openai import OpenAI

# ============================================================
# CONFIGURATION
# ============================================================

client = OpenAI(
    base_url="http://localhost:8007/v1",  # TON PROXY
    api_key="not-needed"  # L'API key est gérée côté serveur
)


# ============================================================
# EXEMPLE 1: Chat simple (non-streaming)
# ============================================================

def chat_simple():
    print("=" * 50)
    print("EXEMPLE 1: Chat simple")
    print("=" * 50)
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tu es un assistant concis."},
            {"role": "user", "content": "Donne-moi 3 conseils pour bien dormir."}
        ],
        stream=False
    )
    
    print(f"Réponse: {response.choices[0].message.content}")
    print(f"Model: {response.model}")
    print(f"ID: {response.id}")
    print()


# ============================================================
# EXEMPLE 2: Chat streaming
# ============================================================

def chat_streaming():
    print("=" * 50)
    print("EXEMPLE 2: Chat streaming")
    print("=" * 50)
    
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Raconte-moi une blague courte."}
        ],
        stream=True
    )
    
    print("Réponse: ", end="", flush=True)
    for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            print(content, end="", flush=True)
    print("\n")


# ============================================================
# EXEMPLE 3: Conversation multi-tours
# ============================================================

def chat_conversation():
    print("=" * 50)
    print("EXEMPLE 3: Conversation multi-tours")
    print("=" * 50)
    
    messages = [
        {"role": "system", "content": "Tu es un prof de maths patient."}
    ]
    
    questions = [
        "C'est quoi une dérivée ?",
        "Donne-moi un exemple simple.",
        "Et pour x² ?"
    ]
    
    for q in questions:
        print(f"User: {q}")
        messages.append({"role": "user", "content": q})
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            stream=False
        )
        
        answer = response.choices[0].message.content
        messages.append({"role": "assistant", "content": answer})
        print(f"Assistant: {answer}\n")


# ============================================================
# EXEMPLE 4: Liste des modèles
# ============================================================

def list_models():
    print("=" * 50)
    print("EXEMPLE 4: Liste des modèles")
    print("=" * 50)
    
    models = client.models.list()
    for model in models.data:
        print(f"  - {model.id}")
    print()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("\n🚀 Client OpenAI → Proxy local (http://localhost:8007/v1)\n")
    
    # Liste des modèles
    list_models()
    
    # Chat simple
    chat_simple()
    
    # Chat streaming
    chat_streaming()
    
    # Conversation
    chat_conversation()
    
    print("✅ Terminé!")
