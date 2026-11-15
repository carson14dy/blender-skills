// Turn a plain-language job description into a build-sequence plan with
// Claude. Uses the official Anthropic SDK (optional dependency) with a JSON
// schema output format, so the viewer always gets a plan it can play.

import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';

export const MODEL = process.env.ROOF_PLAN_MODEL || 'claude-opus-5-5';

const LAYERS = ['oldShingles', 'oldFelt', 'deck', 'deckRepair', 'dripEdge', 'iceWater', 'underlayment', 'starter', 'nails', 'covering', 'ridgeVent', 'ridgeCap'];

const PLAN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['title', 'summary', 'steps'],
  properties: {
    title: { type: 'string' },
    summary: { type: 'string' },
    steps: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'title', 'detail', 'duration', 'camera', 'actions'],
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          detail: { type: 'string' },
          duration: { type: 'number' },
          camera: { type: 'string', enum: ['orbit', 'top', 'none'] },
          actions: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['layer', 'op', 'from', 'to'],
              properties: {
                layer: { type: 'string', enum: LAYERS },
                op: { type: 'string', enum: ['install', 'remove', 'show', 'hide'] },
                from: { type: 'number' },
                to: { type: 'number' },
              },
            },
          },
        },
      },
    },
  },
};

const SYSTEM = `You plan residential re-roofing jobs for a 3D build animation.
The viewer animates layers of a roof model. Each step has a short title, a one or two sentence detail written for a homeowner (plain words, real installation specs where they matter), a duration in animation seconds (1.5 to 10; longer for big steps such as tear-off and field shingles), a camera hint, and actions.
Layers you can animate: ${LAYERS.join(', ')}.
- oldShingles and oldFelt start visible; use op "remove" to tear them off. Everything else starts hidden; use op "install".
- from/to are fractions 0..1 of a layer's build order. dripEdge 0-0.5 is the eaves (installed before ice & water) and 0.5-1 is the rakes (installed over the underlayment). Use 0 and 1 otherwise.
- Install nails together with covering in the same step.
- deckRepair shows replacement sheathing sheets.
- Only include layers the job actually uses. Steps without actions (site protection, inspection, clean-up) are fine.
Follow common manufacturer installation instructions and model codes (IRC R905); do not invent brand names that the job description does not mention.`;

export function credentialsAvailable() {
  if (process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_AUTH_TOKEN || process.env.ANTHROPIC_PROFILE) return true;
  try { return fs.existsSync(path.join(os.homedir(), '.config', 'anthropic')); } catch { return false; }
}

export async function sdkAvailable() {
  try { await import('@anthropic-ai/sdk'); return true; } catch { return false; }
}

/**
 * @param {{job:string, layers?:object[], measure?:object, product?:object}} input
 * @returns {Promise<object>} plan JSON
 */
export async function generatePlan(input) {
  let Anthropic;
  try { ({ default: Anthropic } = await import('@anthropic-ai/sdk')); } catch {
    throw new Error('Install the Anthropic SDK first: npm install (in roof-visualizer).');
  }
  const client = new Anthropic();
  const m = input.measure || {};
  const facts = [
    `Job description: ${String(input.job || '').slice(0, 4000)}`,
    input.product ? `Selected covering: ${input.product.name} (${input.product.category}).` : '',
    m.squares ? `Roof: ${m.squares.toFixed(1)} squares on ${m.planes} planes; eaves ${(m.eaveM / 0.3048).toFixed(0)} ft, rakes ${(m.rakeM / 0.3048).toFixed(0)} ft, ridges ${(m.ridgeM / 0.3048).toFixed(0)} ft, hips ${(m.hipM / 0.3048).toFixed(0)} ft, valleys ${(m.valleyM / 0.3048).toFixed(0)} ft.` : '',
    input.layers?.length ? `Layers in the model: ${input.layers.map((l) => `${l.id} (${l.label}: ${l.spec})`).join('; ')}.` : '',
  ].filter(Boolean).join('\n');

  // Streaming avoids HTTP timeouts on long outputs; finalMessage() returns the whole response.
  // Server-side fallback re-runs a declined request on the model Anthropic recommends.
  const stream = client.beta.messages.stream({
    model: MODEL,
    max_tokens: 16000,
    betas: ['server-side-fallback-2026-07-01'],
    fallbacks: 'default',
    output_config: { effort: 'medium', format: { type: 'json_schema', schema: PLAN_SCHEMA } },
    system: SYSTEM,
    messages: [{ role: 'user', content: `${facts}\n\nWrite the build plan.` }],
  });
  const message = await stream.finalMessage();
  if (message.stop_reason === 'refusal') throw new Error('Claude declined to write this plan. Rephrase the job description and try again.');
  if (message.stop_reason === 'max_tokens') throw new Error('The plan was cut off. Try a shorter job description.');
  const text = message.content.filter((b) => b.type === 'text').map((b) => b.text).join('');
  const plan = JSON.parse(text);
  plan.generator = 'claude';
  plan.model = message.model;
  for (const s of plan.steps) if (s.camera === 'none') s.camera = null;
  return plan;
}

/** Map SDK errors to messages a contractor can act on. */
export async function explainError(e) {
  let Anthropic = null;
  try { ({ default: Anthropic } = await import('@anthropic-ai/sdk')); } catch { /* not installed */ }
  if (Anthropic) {
    if (e instanceof Anthropic.AuthenticationError) return { status: 401, error: 'The Anthropic API key was rejected. Set ANTHROPIC_API_KEY or run "ant auth login".' };
    if (e instanceof Anthropic.RateLimitError) return { status: 429, error: 'Rate limited by the Anthropic API. Wait a minute and try again.' };
    if (e instanceof Anthropic.BadRequestError) return { status: 400, error: `The request was rejected: ${e.message}` };
    if (e instanceof Anthropic.APIError) return { status: 502, error: `Anthropic API error ${e.status ?? ''}: ${e.message}` };
  }
  return { status: 500, error: e.message || String(e) };
}
