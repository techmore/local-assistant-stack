<!-- Licence: CC BY 4.0 -->
# Incident note: a small model with an unrestricted toolset

During the first smoke test of this project the agent framework was run with its default
toolset (terminal, file, browser, code execution and skill management) while driving a 4B local
model, with approval prompts turned off, inside an early version of the evaluation sandbox.

The user message asked the assistant to text a short phrase to a number. The number was a
fictional fixture value and the intended tool was the lab's stand-in `send_message`, which only
appends to an in-memory list.

The model did not find that tool. It searched the tool catalogue, tried three times to write
itself a new "skill" describing how to send messages on the host operating system, and then used
the terminal tool to run a command that asks the system's own messaging application to send the
text. The operating system refused the request because the process had no permission to control
that application, and the command exited with an error. Nothing was sent. The model then looked
for another command-line messaging tool before running out of turns.

What this shows:

- A capable-looking refusal is not the default. Given a shell, a small model will improvise a way
  to act on the real world when its intended tool is missing.
- The only things that stopped a real message were an operating-system permission that happened
  not to be granted and a number that happened to be fictional.

What changed as a result, and is enforced in this repository:

- The model is never given the framework's own terminal, file, browser or computer-use tools.
  Evaluation runs expose only the stand-in tools.
- Every agent process runs inside an OS sandbox that allows writes only to the lab's state
  directories, denies reading the rest of the home directory, allows loopback network only,
  denies inter-application automation and denies executing the usual automation binaries. If no
  sandbox is available the harness refuses to start the agent.
- Sending and deleting go through a confirmation gate enforced in code
  ([confirmation-gate.md](confirmation-gate.md)), so that even a model that decides to send
  cannot do so without an approval recorded outside the model.
