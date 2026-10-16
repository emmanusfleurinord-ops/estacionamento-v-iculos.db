const $ = (id) => document.getElementById(id);

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
    btn.classList.add("active");
    $(btn.dataset.tela).classList.add("active");
    if (btn.dataset.tela === "patio") carregarPatio();
    if (btn.dataset.tela === "relatorio") carregarRelatorio();
  });
});

$("formEntrada").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("erroEntrada").textContent = "";
  $("okEntrada").textContent = "";
  const dados = {
    nome: $("nome").value,
    telefone: $("telefone").value,
    placa: $("placa").value,
    tipo: $("tipo").value,
    marca: $("marca").value,
    modelo: $("modelo").value,
    cor: $("cor").value,
    ano: $("ano").value,
    tamanho: $("tamanho").value,
    tipo_vaga: $("tipo_vaga").value,
    tipo_preco: $("tipo_preco").value
  };
  try {
    const res = await fetch("/entrada", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dados)
    });
    const json = await res.json();
    if (!json.ok) {
      $("erroEntrada").textContent = json.erro || "Não gravou.";
      return;
    }
    $("okEntrada").textContent = json.mensagem + " Gravado no banco.";
    $("formEntrada").reset();
  } catch (err) {
    $("erroEntrada").textContent = "Abra com python3 app.py na porta 8000.";
  }
});

async function carregarPatio() {
  const box = $("listaPatio");
  try {
    const linhas = await fetch("/patio").then((r) => r.json());
    if (!linhas.length) {
      box.textContent = "Nenhum veículo no pátio.";
      return;
    }
    box.innerHTML = linhas.map((item) => `
      <article class="card">
        <div>
          <div class="placa">${item.placa}</div>
          <div>${item.nome} • ${item.marca || ""} ${item.modelo || ""}</div>
          <div class="meta">Vaga ${item.vaga} (${item.tipo_vaga}) • ${item.cor || "sem cor"} • ${item.tipo_preco}</div>
          <div class="meta">Entrada: ${item.entrada}</div>
        </div>
        <button class="btn warn" type="button" data-saida="${item.id}">Registrar saída</button>
      </article>
    `).join("");
  } catch (err) {
    box.textContent = "Não consegui ler o banco.";
  }
}

document.addEventListener("click", async (e) => {
  const id = e.target.dataset.saida;
  if (!id) return;
  const res = await fetch("/saida", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: Number(id) })
  });
  const json = await res.json();
  alert(json.mensagem || json.erro || "Saída registrada.");
  carregarPatio();
});

async function carregarRelatorio() {
  const box = $("listaRelatorio");
  try {
    const linhas = await fetch("/relatorio").then((r) => r.json());
    if (!linhas.length) {
      box.textContent = "Ainda não há movimentações.";
      return;
    }
    box.innerHTML = `
      <table>
        <thead>
          <tr><th>Cliente</th><th>Placa</th><th>Vaga</th><th>Entrada</th><th>Saída</th><th>Valor</th><th>Status</th></tr>
        </thead>
        <tbody>
          ${linhas.map((item) => `
            <tr>
              <td>${item.nome}</td>
              <td>${item.placa}</td>
              <td>${item.vaga}</td>
              <td>${item.entrada}</td>
              <td>${item.saida || "-"}</td>
              <td>${item.valor == null ? "-" : "R$ " + Number(item.valor).toFixed(2)}</td>
              <td>${item.status}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch (err) {
    box.textContent = "Não consegui ler o relatório.";
  }
}