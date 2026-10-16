"""Sistema de estacionamento com SQLite.

No VS Code, rode:

    python3 app.py

Depois abra http://127.0.0.1:8000

O arquivo estacionamento.db abre no DB Browser for SQLite.
"""

import json
import sqlite3
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PASTA = Path(__file__).resolve().parent
BANCO = PASTA / "estacionamento.db"


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conectar():
    conn = sqlite3.connect(BANCO, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def criar_banco():
    with conectar() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            data_ocorrencia DATETIME DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS veiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            placa TEXT NOT NULL UNIQUE,
            cor TEXT,
            marca TEXT,
            modelo TEXT,
            tamanho TEXT,
            tipo TEXT,
            ano INTEGER,
            data_ocorrencia DATETIME DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        );
        CREATE TABLE IF NOT EXISTS vagas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL,
            ocupada INTEGER NOT NULL DEFAULT 0,
            data_ocorrencia DATETIME DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS precos (
            tipo TEXT PRIMARY KEY,
            valor REAL NOT NULL,
            data_ocorrencia DATETIME DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            veiculo_id INTEGER NOT NULL,
            vaga_id INTEGER NOT NULL,
            entrada DATETIME NOT NULL,
            saida DATETIME,
            tipo_preco TEXT NOT NULL,
            valor REAL,
            status TEXT NOT NULL,
            data_ocorrencia DATETIME DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (veiculo_id) REFERENCES veiculos(id),
            FOREIGN KEY (vaga_id) REFERENCES vagas(id)
        );
        """)
        if conn.execute("SELECT COUNT(*) FROM vagas").fetchone()[0] == 0:
            vagas = [(f"N{i}", "normal") for i in range(1, 9)]
            vagas += [(f"P{i}", "preferencial") for i in range(1, 4)]
            vagas += [(f"M{i}", "moto") for i in range(1, 4)]
            vagas += [(f"G{i}", "grande") for i in range(1, 3)]
            conn.executemany("INSERT INTO vagas (codigo, tipo) VALUES (?, ?)", vagas)
        if conn.execute("SELECT COUNT(*) FROM precos").fetchone()[0] == 0:
            conn.executemany("INSERT INTO precos (tipo, valor) VALUES (?, ?)", [
                ("hora", 8.0), ("diaria", 40.0), ("mensal", 280.0), ("anual", 2400.0)
            ])
        for tabela in ("clientes", "veiculos", "vagas", "precos", "movimentacoes"):
            colunas = [linha[1] for linha in conn.execute(f"PRAGMA table_info({tabela})").fetchall()]
            if "data_ocorrencia" not in colunas:
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN data_ocorrencia DATETIME")


def placa_limpa(placa):
    return "".join(ch for ch in str(placa or "").upper() if ch.isalnum())


def calcular_valor(tipo_preco, entrada, saida):
    with conectar() as conn:
        linha = conn.execute("SELECT valor FROM precos WHERE tipo = ?", (tipo_preco,)).fetchone()
    base = float(linha["valor"]) if linha else 0
    ini = datetime.strptime(entrada, "%Y-%m-%d %H:%M:%S")
    fim = datetime.strptime(saida, "%Y-%m-%d %H:%M:%S")
    segundos = max(0, (fim - ini).total_seconds())
    if tipo_preco == "hora":
        horas = max(1, int((segundos + 3599) // 3600))
        return round(horas * base, 2)
    if tipo_preco == "diaria":
        dias = max(1, int((segundos + 86399) // 86400))
        return round(dias * base, 2)
    return round(base, 2)


def listar_patio():
    with conectar() as conn:
        linhas = conn.execute("""
            SELECT m.id, c.nome, c.telefone, v.placa, v.cor, v.marca, v.modelo,
                   v.tamanho, v.tipo, v.ano, g.codigo AS vaga, g.tipo AS tipo_vaga,
                   m.entrada, m.tipo_preco
            FROM movimentacoes m
            JOIN veiculos v ON v.id = m.veiculo_id
            JOIN clientes c ON c.id = v.cliente_id
            JOIN vagas g ON g.id = m.vaga_id
            WHERE m.status = 'estacionado'
            ORDER BY m.id DESC
        """).fetchall()
    return [dict(linha) for linha in linhas]


def listar_relatorio():
    with conectar() as conn:
        linhas = conn.execute("""
            SELECT m.id, c.nome, v.placa, v.modelo, g.codigo AS vaga,
                   m.entrada, m.saida, m.tipo_preco, m.valor, m.status
            FROM movimentacoes m
            JOIN veiculos v ON v.id = m.veiculo_id
            JOIN clientes c ON c.id = v.cliente_id
            JOIN vagas g ON g.id = m.vaga_id
            ORDER BY m.id DESC
        """).fetchall()
    return [dict(linha) for linha in linhas]


def vagas_livres(tipo_vaga):
    with conectar() as conn:
        linhas = conn.execute(
            "SELECT id, codigo, tipo FROM vagas WHERE ocupada = 0 AND tipo = ? ORDER BY codigo",
            (tipo_vaga,),
        ).fetchall()
    return [dict(linha) for linha in linhas]


def registrar_entrada(dados):
    nome = str(dados.get("nome", "")).strip()
    telefone = str(dados.get("telefone", "")).strip()
    placa = placa_limpa(dados.get("placa"))
    if not nome or not placa:
        return {"ok": False, "erro": "Preencha o nome e a placa."}
    tipo_vaga = dados.get("tipo_vaga") or "normal"
    tipo_preco = dados.get("tipo_preco") or "hora"
    with conectar() as conn:
        aberto = conn.execute("""
            SELECT m.id FROM movimentacoes m
            JOIN veiculos v ON v.id = m.veiculo_id
            WHERE v.placa = ? AND m.status = 'estacionado'
        """, (placa,)).fetchone()
        if aberto:
            return {"ok": False, "erro": "Essa placa já está no pátio."}
        vaga = conn.execute(
            "SELECT id, codigo FROM vagas WHERE ocupada = 0 AND tipo = ? ORDER BY codigo LIMIT 1",
            (tipo_vaga,),
        ).fetchone()
        if not vaga:
            return {"ok": False, "erro": "Não há vaga livre desse tipo."}
        cliente = conn.execute(
            "SELECT id FROM clientes WHERE nome = ? AND IFNULL(telefone, '') = ?",
            (nome, telefone),
        ).fetchone()
        if cliente:
            cliente_id = cliente["id"]
        else:
            cur = conn.execute(
                "INSERT INTO clientes (nome, telefone, data_ocorrencia) VALUES (?, ?, ?)",
                (nome, telefone, agora()),
            )
            cliente_id = cur.lastrowid
        veiculo = conn.execute("SELECT id FROM veiculos WHERE placa = ?", (placa,)).fetchone()
        if veiculo:
            veiculo_id = veiculo["id"]
            conn.execute("""
                UPDATE veiculos
                SET cliente_id = ?, cor = ?, marca = ?, modelo = ?, tamanho = ?, tipo = ?, ano = ?
                WHERE id = ?
            """, (
                cliente_id, dados.get("cor"), dados.get("marca"), dados.get("modelo"),
                dados.get("tamanho"), dados.get("tipo"), dados.get("ano") or None, veiculo_id
            ))
        else:
            cur = conn.execute("""
                INSERT INTO veiculos (cliente_id, placa, cor, marca, modelo, tamanho, tipo, ano, data_ocorrencia)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cliente_id, placa, dados.get("cor"), dados.get("marca"), dados.get("modelo"),
                dados.get("tamanho"), dados.get("tipo"), dados.get("ano") or None, agora()
            ))
            veiculo_id = cur.lastrowid
        momento = agora()
        conn.execute("""
            INSERT INTO movimentacoes (veiculo_id, vaga_id, entrada, tipo_preco, status, data_ocorrencia)
            VALUES (?, ?, ?, ?, 'estacionado', ?)
        """, (veiculo_id, vaga["id"], momento, tipo_preco, momento))
        conn.execute("UPDATE vagas SET data_ocorrencia = ? WHERE id = ?", (momento, vaga["id"]))
        conn.execute("UPDATE vagas SET ocupada = 1 WHERE id = ?", (vaga["id"],))
    print("Entrada gravada:", nome, placa, vaga["codigo"])
    return {"ok": True, "mensagem": f"Entrada gravada. Vaga {vaga['codigo']}."}


def registrar_saida(mov_id):
    with conectar() as conn:
        mov = conn.execute("SELECT * FROM movimentacoes WHERE id = ? AND status = 'estacionado'", (mov_id,)).fetchone()
        if not mov:
            return {"ok": False, "erro": "Movimentação não encontrada."}
        saida = agora()
        valor = calcular_valor(mov["tipo_preco"], mov["entrada"], saida)
        conn.execute(
            "UPDATE movimentacoes SET saida = ?, valor = ?, status = 'finalizado' WHERE id = ?",
            (saida, valor, mov_id),
        )
        conn.execute("UPDATE vagas SET ocupada = 0 WHERE id = ?", (mov["vaga_id"],))
    print("Saída gravada:", mov_id, valor)
    return {"ok": True, "mensagem": f"Saída gravada. Valor: R$ {valor:.2f}", "valor": valor}


class ProjetoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PASTA), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def json_resposta(self, dados, status=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def ler_json(self):
        tamanho = int(self.headers.get("Content-Length", "0"))
        bruto = self.rfile.read(tamanho).decode("utf-8")
        return json.loads(bruto or "{}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        caminho = urlparse(self.path).path
        if caminho == "/patio":
            return self.json_resposta(listar_patio())
        if caminho == "/relatorio":
            return self.json_resposta(listar_relatorio())
        if caminho == "/vagas":
            return self.json_resposta(vagas_livres(self.path.split("tipo=")[-1] if "tipo=" in self.path else "normal"))
        return super().do_GET()

    def do_POST(self):
        caminho = urlparse(self.path).path
        dados = self.ler_json()
        if caminho == "/entrada":
            return self.json_resposta(registrar_entrada(dados))
        if caminho == "/saida":
            return self.json_resposta(registrar_saida(int(dados.get("id", 0))))
        self.send_error(404)


def main():
    criar_banco()
    print("Banco SQLite:", BANCO)
    print("Abra http://127.0.0.1:8000")
    print("No DB Browser, abra estacionamento.db")
    servidor = ThreadingHTTPServer(("127.0.0.1", 8000), ProjetoHandler)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()