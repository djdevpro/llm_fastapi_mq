/**
 * Exemple: Client OpenAI (Node.js) pointant vers le proxy local.
 * 
 * Usage:
 *   npm install openai
 *   node examples/client_openai.js
 */

import OpenAI from 'openai';

// ============================================================
// CONFIGURATION
// ============================================================

const client = new OpenAI({
  baseURL: 'http://localhost:8007/v1',  // TON PROXY
  apiKey: 'not-needed'
});

// ============================================================
// EXEMPLE 1: Chat streaming
// ============================================================

async function chatStreaming() {
  console.log('='.repeat(50));
  console.log('Chat streaming');
  console.log('='.repeat(50));
  
  const stream = await client.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [
      { role: 'user', content: 'Raconte-moi une blague courte.' }
    ],
    stream: true
  });

  process.stdout.write('Réponse: ');
  for await (const chunk of stream) {
    const content = chunk.choices[0]?.delta?.content || '';
    process.stdout.write(content);
  }
  console.log('\n');
}

// ============================================================
// EXEMPLE 2: Chat simple
// ============================================================

async function chatSimple() {
  console.log('='.repeat(50));
  console.log('Chat simple');
  console.log('='.repeat(50));
  
  const response = await client.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [
      { role: 'user', content: 'Donne 3 conseils pour bien dormir.' }
    ],
    stream: false
  });

  console.log('Réponse:', response.choices[0].message.content);
  console.log('Model:', response.model);
  console.log();
}

// ============================================================
// MAIN
// ============================================================

async function main() {
  console.log('\n🚀 Client OpenAI (Node.js) → Proxy local\n');
  
  await chatStreaming();
  await chatSimple();
  
  console.log('✅ Terminé!');
}

main().catch(console.error);



