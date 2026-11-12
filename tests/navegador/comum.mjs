// O que os testes de navegador dividem: subir o Chrome sem janela, falar CDP
// com ele, conferir, fotografar — e ESPERAR A TELA SOSSEGAR.
//
// A espera é o ponto. Os roteiros esperavam tempo FIXO depois de cada gesto
// (`setTimeout(r, 300)`), e sob a carga da suíte inteira a resposta do
// servidor chegava depois: o `.calc-modelo` «Zap AG» ainda não estava na
// lista e o `.click()` caía sobre `undefined` (caça de bugs T1, 11/11/2026).
// Agora todo `fetch` da página é contado (`__emVoo`) e `__ocioso()` só volta
// quando não há pedido em voo há 200 ms — com teto, para uma tela que fica
// pedindo sem parar não travar o roteiro. O tempo fixo continua como MÍNIMO
// (ele cobre os `setTimeout` de digitação da própria tela), e a espera da
// rede vem depois dele.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const CHROMES = ["C:/Program Files/Google/Chrome/Application/chrome.exe",
                        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
                        "/usr/bin/google-chrome", "/usr/bin/chromium"];

//: Posto em TODO documento antes dos scripts dele (inclusive nos quadros).
const CONTADOR = `(() => {
  if (window.__emVoo) return;
  let n = 0;
  const original = window.fetch.bind(window);
  window.fetch = (...a) => { n++; return original(...a).finally(() => { n--; }); };
  window.__emVoo = () => n;
  window.__ocioso = async (quieto = 200, teto = 20000) => {
    const fim = Date.now() + teto; let desde = null;
    while (Date.now() < fim) {
      if (n === 0) { desde = desde ?? Date.now(); if (Date.now() - desde >= quieto) return true; }
      else desde = null;
      await new Promise((r) => setTimeout(r, 25));
    }
    return false;
  };
  window.__esperar = async (f, teto = 20000) => {
    const fim = Date.now() + teto;
    while (Date.now() < fim) {
      try { const v = f(); if (v) return v; } catch (_e) { /* ainda não */ }
      await new Promise((r) => setTimeout(r, 50));
    }
    return null;
  };
})()`;

//: Espera fixa MAIS a rede sossegar, para usar dentro de `avaliar`.
export const P = (ms) => `new Promise(r => setTimeout(r, ${ms})).then(() => window.__ocioso && window.__ocioso())`;

export async function abrirChrome({ porta, prefixo, fotos, largura = 1600, altura = 1000 }) {
  const chromePath = CHROMES.find((c) => existsSync(c));
  if (!chromePath) { console.log("SEM CHROME"); process.exit(77); }
  mkdirSync(fotos, { recursive: true });
  const perfil = join(tmpdir(), `osclab-${prefixo}-cdp-${porta}`);
  const chrome = spawn(chromePath, ["--headless=new", "--disable-gpu", "--hide-scrollbars",
    `--remote-debugging-port=${porta}`, `--user-data-dir=${perfil}`,
    `--window-size=${largura},${altura}`, "about:blank"], { stdio: "ignore" });
  const espera = (ms) => new Promise((r) => setTimeout(r, ms));
  let alvo;
  // Sob carga o Chrome demora a abrir a porta: até 30 s, e erro claro se não.
  for (let i = 0; i < 120 && !alvo; i++) {
    try { alvo = (await (await fetch(`http://127.0.0.1:${porta}/json`)).json()).find((t) => t.type === "page"); }
    catch { /* ainda subindo */ }
    if (!alvo) await espera(250);
  }
  if (!alvo) { console.log("o Chrome não abriu a porta de depuração"); chrome.kill(); process.exit(1); }
  const ws = new WebSocket(alvo.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let seq = 0; const pend = new Map(); const erros = []; const falhas = [];
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); return; }
    if (m.method === "Runtime.exceptionThrown") erros.push((m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text).split("\n")[0]);
    if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error") erros.push(m.params.args.map((a) => a.value ?? a.description).join(" "));
  });
  const cdp = (method, params = {}) => new Promise((r) => { const id = ++seq; pend.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
  await cdp("Runtime.enable"); await cdp("Page.enable");
  await cdp("Page.addScriptToEvaluateOnNewDocument", { source: CONTADOR });
  await cdp("Emulation.setDeviceMetricsOverride", { width: largura, height: altura, deviceScaleFactor: 1, mobile: false });
  const avaliar = async (expr) => {
    const r = await cdp("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) erros.push("avaliar: " + (r.result.exceptionDetails.exception?.description || "").split("\n")[0]);
    return r.result?.result?.value;
  };
  const ocioso = () => avaliar("window.__ocioso ? window.__ocioso() : true");
  //: Espera fixa e depois a rede sossegar — o `espera` dos roteiros.
  const assentar = async (ms) => { await espera(ms); await ocioso(); };
  const confere = (ok, oque) => { if (!ok) falhas.push(oque); console.log(`${ok ? "ok " : "FALHA"} ${oque}`); };
  const foto = async (nome) => {
    const r = await cdp("Page.captureScreenshot", { format: "png" });
    writeFileSync(join(fotos, nome), Buffer.from(r.result.data, "base64"));
  };
  //: Navega e espera a página montar: o documento carregado, um gráfico na
  //: tela (ou o teto) e a rede quieta.
  const navegar = async (url, pronto = "document.querySelector('section.grafico')") => {
    await cdp("Page.navigate", { url });
    await espera(300);
    await avaliar(`(async () => { await (window.__esperar ? window.__esperar(() => document.readyState === 'complete' && (${pronto}), 30000) : null);
      if (window.__ocioso) await window.__ocioso(); return 1; })()`);
  };
  const terminar = () => {
    confere(erros.length === 0, `sem erro no console${erros.length ? ": " + erros.slice(0, 3).join(" | ") : ""}`);
    ws.close();
    chrome.kill();
    console.log(falhas.length ? `\n${falhas.length} FALHA(S)` : "\ntudo certo");
    process.exit(falhas.length ? 1 : 0);
  };
  return { cdp, avaliar, confere, foto, espera, assentar, ocioso, navegar, terminar, erros, falhas };
}
