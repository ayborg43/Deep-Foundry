import { invoke } from "@tauri-apps/api/core";

const status = document.querySelector<HTMLParagraphElement>("#status")!;
document.querySelector("#grant")!.addEventListener("click", async () => {
  const path = document.querySelector<HTMLInputElement>("#folder")!.value;
  try { await invoke("grant_folder", { path }); status.textContent = `Granted access to ${path}`; }
  catch (error) { status.textContent = String(error); }
});
document.querySelector("#propose")!.addEventListener("click", async () => {
  const command = document.querySelector<HTMLInputElement>("#command")!.value;
  try {
    const token = await invoke<string>("propose_terminal", { command });
    const proposal = document.querySelector<HTMLParagraphElement>("#proposal")!;
    proposal.textContent = `Command: ${command}`;
    const approve = document.createElement("button"); approve.textContent = "Approve once";
    approve.onclick = async () => { status.textContent = await invoke<string>("execute_terminal", { token }); approve.remove(); };
    proposal.append(document.createElement("br"), approve);
  } catch (error) { status.textContent = String(error); }
});
