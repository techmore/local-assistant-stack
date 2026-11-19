<!-- Licence: CC BY 4.0 -->
# Would a 27B model do better? A check, not a measurement

Checked on 2026-11-18 against the Hugging Face API. **Nothing was downloaded or run.** Sizes are
from the API's file listings (decimal GB). Memory figures are estimates and are labelled as such.

## The model

`RadixArk/DaisyRose-27B`: a fine-tune of `Qwen/Qwen3.8-27B` for agentic terminal and coding work,
Apache-2.0, published 2026-11-18. 27.8 billion parameters including a small vision encoder; 64
layers of which 16 use full attention and 48 a linear-attention variant; 262,144-token context.
Thinking is on by default at its highest effort. Tool calls use the Qwen3-coder XML format. The
card's benchmark gains over the base model are the publisher's own numbers on coding and terminal
benchmarks; none was measured on a quantised build, and none is a personal-assistant task.

## Quantised builds that exist

All three appeared within a day of the release and had no downloads recorded when checked, so
none has a track record.

| repository | format | 4-bit size | smaller builds |
|---|---|---|---|
| `bartowski/RadixArk_DaisyRose-27B-GGUF` | GGUF, imatrix | Q4_K_M 17.33 GB (Q4_K_S 16.26, IQ4_XS 15.37) | Q3_K_M 13.33, IQ2_XXS 8.76; Q8_0 is 29.05 |
| `angt/DaisyRose-27B-GGUF` | GGUF | Q4_K_M 17.01 GB | none |
| `slackcrow/DaisyRose-27B-oQ4h-mtp` | MLX, mixed 4-bit | 17.5 GB | none; its card names a specific MLX runtime, and whether stock `mlx_lm` loads it was not verified |

The original weights are 55.6 GB, so converting locally is unnecessary and would need about 130 GB
of disk.

## What a 4-bit build needs (estimate)

Weights 17.0 to 17.3 GB, plus a key/value cache that grows with context only for the 16
full-attention layers (about 65 KB per token at 16-bit, so roughly 0.5 GB at 8K, 2.1 GB at 32K
and 4.3 GB at 64K), plus under 1 GB of buffers. Roughly **19 GB at 8K context and 22 to 23 GB at
64K**. Hermes Agent refuses contexts under 64,000 tokens, so the larger figure is the one that
applies at the Hermes level. Not measured.

## Where it could run

| machine | verdict |
|---|---|
| Apple Silicon laptop, 32 GB (the machine this lab ran on) | Fits in memory at 4-bit with a 64K context, with about 9 GB left for everything else, so not alongside other heavy work. It did **not** fit the rules for this check: the file is 17 GB, which would have left less free disk than the lab keeps in reserve. Expect a small fraction of the 4B model's speed; not measured. |
| Apple Silicon mini, 16 GB | Not at 4-bit or 3-bit. Only the 2-bit builds (8.8 to 10.8 GB) fit beside the system, with a short context, and 2-bit quantisation of a model this size usually costs much of what the size buys. Not recommended. |
| x86 mini PC, CPU only | It will load if the machine has about 24 GB of free RAM, but a first Hermes turn is about 5,000 prompt tokens and every tool step is another turn. On CPU that is likely minutes per request. Usable for unattended batch jobs at best, not for an assistant. Not measured. |

## What a fair comparison with the 4B model would be

- The same harness, tool schemas, gate and the same task set (`third`, or better a fresh one),
  three runs per task with the same seeds, pass rates compared paired by task with a bootstrap
  interval, and the unsafe-action and injection counts reported separately.
- Both thinking settings for the 27B model (its default is on at the highest effort; the 4B
  results are with thinking off), and a check first that the server's chat template turns its XML
  tool calls into structured ones. A model that fails only on call formatting has not been
  compared.
- The base `Qwen3.8-27B` at the same quantisation as a third arm. Without it, "bigger" and "this
  fine-tune" cannot be told apart, and the fine-tune was trained for terminal work, not for
  calendar, message and reminder tasks.
- Cost next to accuracy: memory, time to first token cold and warm, seconds per task. The question
  is not whether 27B scores higher but whether the gain is worth about seven times the memory and
  a slower answer, compared with fixing tools or fine-tuning the 4B model.
- The 4B model at 8-bit as a control for quantisation, since the 27B model would run at 4-bit.
