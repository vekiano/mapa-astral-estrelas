# -*- coding: utf-8 -*-
"""
Mapa Astral Completo - Vercel
Com cálculo de aspectos, trânsitos, VOC e busca de cidades
"""

import os
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

from flask import Flask, request, jsonify

try:
    import swisseph as swe
except:
    pass

app = Flask(__name__)

# ========== CONSTANTES ==========

ASPECTOS = {
    'CJN': (0.0, 8.0), 'OPO': (180.0, 8.0), 'TRI': (120.0, 8.0),
    'SQR': (90.0, 6.0), 'SXT': (60.0, 6.0), 'QCX': (150.0, 3.0),
    'SSQ': (45.0, 2.0), 'SQQ': (135.0, 2.0),
}

ORBES_PADRAO = {
    0.0: 8.0, 45.0: 2.0, 60.0: 6.0, 90.0: 6.0, 120.0: 8.0,
    135.0: 2.0, 150.0: 3.0, 180.0: 8.0
}

SIGNOS = ['AR', 'TA', 'GE', 'CA', 'LE', 'VI', 'LI', 'SC', 'SG', 'CP', 'AQ', 'PI']

PLANETAS = {
    'SOL': swe.SUN, 'LUA': swe.MOON, 'MER': swe.MERCURY, 'VEN': swe.VENUS,
    'MAR': swe.MARS, 'JUP': swe.JUPITER, 'SAT': swe.SATURN, 'URA': swe.URANUS,
    'NET': swe.NEPTUNE, 'PLU': swe.PLUTO, 'TNN': swe.TRUE_NODE,
}

PLANETA_REV = {v: k for k, v in PLANETAS.items()}


# ========== FUNÇÕES AUXILIARES ==========

def graus_para_dms(graus: float) -> str:
    graus = graus % 360.0
    g = int(graus)
    m = int((graus - g) * 60)
    s = int(((graus - g) * 60 - m) * 60)
    return f"{g:02d}°{m:02d}'{s:02d}\""


def graus_para_signo_posicao(graus: float) -> Tuple[str, str]:
    graus = graus % 360.0
    idx = int(graus / 30.0)
    pos_no_signo = graus % 30.0
    return SIGNOS[idx], graus_para_dms(pos_no_signo)


def angular_difference(a: float, b: float) -> float:
    d = abs((a % 360.0) - (b % 360.0))
    return d if d <= 180.0 else 360.0 - d


def dt_to_jd_utc(dt_utc: datetime) -> float:
    frac = (dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0)
    jd_utc = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, frac, 1)
    return jd_utc


def jd_para_datetime(jd: float, tz_offset: float = 0.0) -> datetime:
    year, month, day, hour = swe.revjul(jd + tz_offset / 24.0)
    hour_int = int(hour)
    minute = int((hour - hour_int) * 60)
    second = int(((hour - hour_int) * 60 - minute) * 60)
    return datetime(year, month, day, hour_int, minute, second)


def calcular_posicao_planeta(jd: float, planeta: int) -> float:
    pos, _ = swe.calc_ut(jd, planeta)
    return float(pos[0]) % 360.0


def calcular_declinacao_planeta(jd: float, planeta: int) -> float:
    eq, _ = swe.calc_ut(jd, planeta, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)
    return float(eq[1])


def dias_para_hms(dias: float) -> str:
    dias = abs(dias)
    horas = dias * 24
    h = int(horas)
    minutos = (horas - h) * 60
    m = int(minutos)
    segundos = int((minutos - m) * 60)
    return f"{h:02d}:{m:02d}:{segundos:02d}"


# ========== CLASSES ==========

@dataclass
class Corpo:
    nome: str
    lon: float
    lat: float
    vel: float
    mov: str
    signo: str
    pos_str: str
    decl: Optional[float] = None


@dataclass
class Transito:
    jd_exato: float
    planeta1: int
    planeta2: int
    aspecto: float
    pos_planeta1: float
    pos_planeta2: float
    orbe: float
    tipo: str


@dataclass
class EventoAstral:
    jd_exato: float
    tipo: str
    descricao: str

    def __lt__(self, other):
        return self.jd_exato < other.jd_exato


# ========== BUSCA DE TRÂNSITOS ==========

def determinar_intervalo(planeta1: int, planeta2: int) -> float:
    planeta_lento = max(planeta1, planeta2)
    intervalos = {
        swe.MOON: 0.01, swe.MERCURY: 0.05, swe.VENUS: 0.05, swe.SUN: 0.05,
        swe.MARS: 0.1, swe.JUPITER: 0.2, swe.SATURN: 0.5, swe.URANUS: 1.0,
        swe.NEPTUNE: 1.0, swe.PLUTO: 1.0, swe.TRUE_NODE: 0.5,
    }
    return intervalos.get(planeta_lento, 0.5)


def buscar_transito_exato(jd_inicio: float, jd_fim: float, planeta1: int, planeta2: int,
                          angulo_aspecto: float, orbe: float) -> Tuple[float, float]:
    NUM_SAMPLES = 12
    BISSECCOES_MAX = 6
    ORBE_LIMITE = orbe * 1.5

    def calcular_orbe_atual(jd: float) -> float:
        p1 = calcular_posicao_planeta(jd, planeta1)
        p2 = calcular_posicao_planeta(jd, planeta2)
        diff = angular_difference(p1, p2)
        return diff - angulo_aspecto

    delta_tempo = (jd_fim - jd_inicio) / (NUM_SAMPLES - 1)
    amostras = []
    melhor_orbe = 999
    melhor_jd = 0

    for i in range(NUM_SAMPLES):
        jd_sample = jd_inicio + i * delta_tempo
        orbe_val = abs(calcular_orbe_atual(jd_sample))
        amostras.append((jd_sample, orbe_val))
        if orbe_val < melhor_orbe:
            melhor_orbe = orbe_val
            melhor_jd = jd_sample

    if melhor_orbe > ORBE_LIMITE:
        return 0, 999

    jd1, jd2 = 0, 0
    for i in range(1, NUM_SAMPLES - 1):
        if amostras[i - 1][1] > amostras[i][1] < amostras[i + 1][1]:
            jd1, jd2 = amostras[i - 1][0], amostras[i + 1][0]
            break

    if jd1 == 0:
        idx = [i for i, (jd, _) in enumerate(amostras) if jd == melhor_jd][0]
        idx1 = max(0, idx - 1)
        idx2 = min(NUM_SAMPLES - 1, idx + 1)
        jd1, jd2 = amostras[idx1][0], amostras[idx2][0]

    for _ in range(BISSECCOES_MAX):
        jd_meio = (jd1 + jd2) / 2
        orbe_meio = abs(calcular_orbe_atual(jd_meio))
        if orbe_meio < melhor_orbe:
            melhor_orbe = orbe_meio
            melhor_jd = jd_meio
        if orbe_meio <= 0.001:
            return jd_meio, orbe_meio

        orbe1 = abs(calcular_orbe_atual(jd1))
        orbe2 = abs(calcular_orbe_atual(jd2))
        if orbe1 < orbe2:
            jd2 = jd_meio
        else:
            jd1 = jd_meio

    return melhor_jd, melhor_orbe if melhor_orbe <= orbe else (0, 999)


# ========== MAPA ASTRAL ==========

class MapaAstral:
    def __init__(self, nome_mapa: str, dia, mes, ano, hora, minuto, segundo,
                 latitude_dec: float, longitude_dec: float, timezone_horas: float,
                 cidade: str = '', estado: str = '', pais: str = ''):
        self.nome_mapa = nome_mapa.strip()
        self.dia, self.mes, self.ano = dia, mes, ano
        self.hora, self.minuto, self.segundo = hora, minuto, segundo
        self.latitude, self.longitude = latitude_dec, longitude_dec
        self.timezone_horas = timezone_horas
        self.cidade, self.estado, self.pais = cidade, estado, pais

        self.dt_local = datetime(ano, mes, dia, hora, minuto, segundo)
        self.dt_utc = self.dt_local - timedelta(hours=timezone_horas)
        self.jd = dt_to_jd_utc(self.dt_utc)

        self.planetas: Dict[str, Corpo] = {}
        self.casas: Dict[int, Dict] = {}
        self.aspectos_natais: List[Dict] = []
        self.transitos: List[Transito] = []
        self.eventos_astral: List[EventoAstral] = []

        swe.set_ephe_path(None)

    def calcular_planetas(self) -> None:
        self.planetas.clear()
        for nome, code in PLANETAS.items():
            pos, _ = swe.calc_ut(self.jd, code)
            lon, lat, lon_speed = float(pos[0]), float(pos[1]), float(pos[3])
            mov = 'DIR' if lon_speed >= 0 else 'RET'
            signo, pos_str = graus_para_signo_posicao(lon)
            self.planetas[nome] = Corpo(nome, lon, lat, lon_speed, mov, signo, pos_str)

    def calcular_casas(self) -> None:
        self.casas.clear()
        casas, ascmc = swe.houses(self.jd, self.latitude, self.longitude, b'R')
        for i in range(12):
            num = i + 1
            lon = float(casas[i])
            s, p = graus_para_signo_posicao(lon)
            self.casas[num] = {'longitude': lon, 'signo': s, 'posicao': p}

    def calcular_aspectos(self) -> None:
        self.aspectos_natais.clear()
        nomes = list(PLANETAS.keys())

        for i, p1_nome in enumerate(nomes):
            for p2_nome in nomes[i + 1:]:
                if p1_nome not in self.planetas or p2_nome not in self.planetas:
                    continue

                p1 = self.planetas[p1_nome]
                p2 = self.planetas[p2_nome]
                dif = angular_difference(p1.lon, p2.lon)

                for cod, (alvo, orbe) in ASPECTOS.items():
                    gap = abs(dif - alvo)
                    if gap <= orbe:
                        sig1, pos1 = graus_para_signo_posicao(p1.lon)
                        sig2, pos2 = graus_para_signo_posicao(p2.lon)

                        self.aspectos_natais.append({
                            'p1': p1_nome, 'p2': p2_nome, 'cod': cod, 'orbe': gap,
                            'pos1': pos1, 'sig1': sig1, 'pos2': pos2, 'sig2': sig2,
                        })

    def calcular_transitos(self, dias_margem: int = 2) -> None:
        self.transitos.clear()

        dt_inicio = self.dt_utc - timedelta(days=dias_margem)
        dt_fim = self.dt_utc + timedelta(days=dias_margem)
        jd_inicio = dt_to_jd_utc(dt_inicio)
        jd_fim = dt_to_jd_utc(dt_fim)

        planetas_list = list(PLANETAS.keys())
        for i, p1_nome in enumerate(planetas_list):
            for p2_nome in planetas_list[i + 1:]:
                p1, p2 = PLANETAS[p1_nome], PLANETAS[p2_nome]

                for aspecto_deg, orbe in ORBES_PADRAO.items():
                    intervalo = determinar_intervalo(p1, p2)
                    jd_atual = jd_inicio

                    while jd_atual < jd_fim:
                        jd_prox = min(jd_atual + intervalo, jd_fim)

                        pos1 = calcular_posicao_planeta(jd_atual, p1)
                        pos2 = calcular_posicao_planeta(jd_atual, p2)
                        diff_atual = angular_difference(pos1, pos2)

                        pos1_prox = calcular_posicao_planeta(jd_prox, p1)
                        pos2_prox = calcular_posicao_planeta(jd_prox, p2)
                        diff_prox = angular_difference(pos1_prox, pos2_prox)

                        gap_atual = abs(diff_atual - aspecto_deg)
                        gap_prox = abs(diff_prox - aspecto_deg)

                        if min(gap_atual, gap_prox) <= orbe:
                            jd_exato, orbe_final = buscar_transito_exato(jd_atual, jd_prox, p1, p2, aspecto_deg, orbe)

                            if jd_exato > 0 and jd_inicio <= jd_exato <= jd_fim and orbe_final < 0.05:
                                pos1_ex = calcular_posicao_planeta(jd_exato, p1)
                                pos2_ex = calcular_posicao_planeta(jd_exato, p2)
                                trans = Transito(jd_exato, p1, p2, aspecto_deg, pos1_ex, pos2_ex, orbe_final, 'aspecto')
                                self.transitos.append(trans)

                        jd_atual = jd_prox

        self.transitos.sort(key=lambda x: x.jd_exato)

    def compilar_eventos_astral(self) -> None:
        self.eventos_astral.clear()

        for trans in self.transitos:
            p1_nome = PLANETA_REV.get(trans.planeta1, f'PL{trans.planeta1}')
            p2_nome = PLANETA_REV.get(trans.planeta2, f'PL{trans.planeta2}')

            sig1, pos1 = graus_para_signo_posicao(trans.pos_planeta1)
            sig2, pos2 = graus_para_signo_posicao(trans.pos_planeta2)

            asp_cod = None
            for cod, (alvo, _) in ASPECTOS.items():
                if abs(trans.aspecto - alvo) < 0.1:
                    asp_cod = cod
                    break
            asp_cod = asp_cod or '???'

            descricao = f"[{p1_nome} {asp_cod} {p2_nome}] - {pos1} {sig1} / {pos2} {sig2} - {trans.orbe:.5f}"
            evento = EventoAstral(trans.jd_exato, 'aspecto', descricao)
            self.eventos_astral.append(evento)

        self.eventos_astral.sort()

    def gerar_relatorio(self) -> str:
        self.calcular_planetas()
        self.calcular_casas()
        self.calcular_aspectos()
        self.calcular_transitos()
        self.compilar_eventos_astral()

        rel = []
        rel.append("=" * 100)
        rel.append(self.nome_mapa or "MAPA ASTRAL COMPLETO")
        rel.append("=" * 100)
        rel.append(
            f"Data: {self.dia:02d}/{self.mes:02d}/{self.ano}  Hora: {self.hora:02d}:{self.minuto:02d}:{self.segundo:02d} (UTC {self.timezone_horas:+.2f}h)")
        if any([self.cidade, self.estado, self.pais]):
            rel.append(f"Local: {self.cidade} / {self.estado} / {self.pais}")
        rel.append(f"Latitude: {self.latitude:.6f}°  Longitude: {self.longitude:.6f}°")
        rel.append("=" * 100)
        rel.append("")

        rel.append("PLANETAS:")
        rel.append("-" * 100)
        for nome in PLANETAS.keys():
            if nome in self.planetas:
                c = self.planetas[nome]
                rel.append(f"{nome:3s} [{c.pos_str} {c.signo}] {c.mov}")

        rel.append("")
        rel.append("CASAS ASTROLÓGICAS:")
        rel.append("-" * 100)
        for num in range(1, 13):
            c = self.casas[num]
            rel.append(f"Casa {num:2d}: {c['posicao']} {c['signo']}")

        rel.append("")
        rel.append(f"ASPECTOS DO MAPA ASTRAL ({len(self.aspectos_natais)}):")
        rel.append("-" * 100)
        for asp in sorted(self.aspectos_natais, key=lambda x: x['orbe']):
            linha = f"{asp['p1']:3s} [{asp['pos1']} {asp['sig1']}] {asp['cod']} {asp['p2']:3s} [{asp['pos2']} {asp['sig2']}] - Orbe: {asp['orbe']:.2f}°"
            rel.append(linha)

        if self.eventos_astral:
            rel.append("")
            rel.append("=" * 100)
            rel.append(f"TRÂNSITOS DO PERÍODO ({len(self.eventos_astral)}):")
            rel.append("-" * 100)

            momento_mapa = self.jd
            rel_mostrou_mapa = False

            for evento in self.eventos_astral:
                if not rel_mostrou_mapa and evento.jd_exato >= momento_mapa:
                    dt_mapa = jd_para_datetime(momento_mapa, self.timezone_horas)
                    rel.append(f"{dt_mapa.strftime('%d/%m/%Y %H:%M:%S')} <-------- MOMENTO DO MAPA ASTRAL")
                    rel_mostrou_mapa = True

                dt_evento = jd_para_datetime(evento.jd_exato, self.timezone_horas)
                dt_str = dt_evento.strftime('%d/%m/%Y %H:%M:%S')
                rel.append(f"{dt_str} - {evento.descricao}")

            if not rel_mostrou_mapa:
                dt_mapa = jd_para_datetime(momento_mapa, self.timezone_horas)
                rel.append(f"{dt_mapa.strftime('%d/%m/%Y %H:%M:%S')} <-------- MOMENTO DO MAPA ASTRAL")

        rel.append("")
        rel.append("=" * 100)
        return "\n".join(rel)


# ========== ROTAS ==========

@app.route('/')
def index():
    now = datetime.now()
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Mapa Astral Online</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 700px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                padding: 40px;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            }}
            h1 {{
                text-align: center;
                color: #333;
                margin-bottom: 30px;
                font-size: 28px;
            }}
            fieldset {{
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 20px;
            }}
            legend {{
                padding: 0 10px;
                color: #667eea;
                font-weight: 600;
            }}
            .row {{
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 10px;
            }}
            input {{
                width: 100%;
                padding: 10px;
                margin: 8px 0;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 14px;
            }}
            input:focus {{
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }}
            button {{
                width: 100%;
                padding: 12px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                cursor: pointer;
                font-size: 16px;
                margin-top: 10px;
            }}
            button:hover {{
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
            }}
            .resultado {{
                margin-top: 30px;
                padding: 20px;
                background: #f0f9ff;
                border-radius: 8px;
                display: none;
                max-height: 500px;
                overflow-y: auto;
            }}
            .resultado pre {{
                font-family: 'Courier New', monospace;
                font-size: 11px;
                color: #1e3a8a;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            .loading {{
                display: none;
                text-align: center;
                color: #667eea;
                font-weight: 600;
            }}
            #cidades {{
                max-height: 150px;
                overflow-y: auto;
                border: 1px solid #ddd;
                border-radius: 4px;
                display: none;
                background: white;
                position: absolute;
                z-index: 10;
                width: 90%;
                margin-top: 2px;
            }}
            .cidade-item {{
                padding: 8px;
                cursor: pointer;
                border-bottom: 1px solid #eee;
            }}
            .cidade-item:hover {{
                background: #f0f9ff;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌙 Mapa Astral Online</h1>

            <form id="mapForm">
                <fieldset>
                    <legend>Identificação</legend>
                    <input type="text" id="nome" placeholder="Nome completo" value="Mapa do Momento" required>
                    <div style="position: relative;">
                        <input type="text" id="cidade" placeholder="Cidade" value="Brasília" required>
                        <div id="cidades"></div>
                    </div>
                    <input type="text" id="estado" placeholder="Estado/UF" value="DF" required>
                </fieldset>

                <fieldset>
                    <legend>Data e Hora de Nascimento</legend>
                    <div class="row">
                        <input type="number" id="dia" min="1" max="31" value="{now.day}" required>
                        <input type="number" id="mes" min="1" max="12" value="{now.month}" required>
                        <input type="number" id="ano" min="1900" max="2100" value="{now.year}" required>
                    </div>
                    <div class="row">
                        <input type="number" id="hora" min="0" max="23" value="{now.hour}" required>
                        <input type="number" id="minuto" min="0" max="59" value="{now.minute}" required>
                        <input type="number" id="segundo" min="0" max="59" value="{now.second}" required>
                    </div>
                </fieldset>

                <fieldset>
                    <legend>Localização</legend>
                    <input type="number" id="latitude" step="0.01" value="-15.77" placeholder="Latitude" required>
                    <input type="number" id="longitude" step="0.01" value="-47.92" placeholder="Longitude" required>
                    <input type="number" id="timezone" step="0.5" value="-3" placeholder="UTC (ex: -3)" required>
                </fieldset>

                <button type="submit">CALCULAR MAPA ASTRAL</button>
            </form>

            <div class="loading" id="loading">Calculando mapa astral... ⏳</div>

            <div id="resultado" class="resultado">
                <button onclick="fecharResultado()" style="width: 100%; margin-bottom: 10px;">Fechar</button>
                <pre id="textoResultado"></pre>
            </div>
        </div>

        <script>
            // Busca de cidades
            document.getElementById('cidade').addEventListener('input', async (e) => {{
                const query = e.target.value;
                if (query.length < 2) {{
                    document.getElementById('cidades').style.display = 'none';
                    return;
                }}

                try {{
                    const res = await fetch(`/api/cidades?q=${{query}}`);
                    const cidades = await res.json();

                    const div = document.getElementById('cidades');
                    div.innerHTML = '';

                    if (cidades.length > 0) {{
                        cidades.forEach(c => {{
                            const item = document.createElement('div');
                            item.className = 'cidade-item';
                            item.textContent = `${{c.city}}, ${{c.state}} - ${{c.country}}`;
                            item.onclick = () => {{
                                document.getElementById('cidade').value = c.city;
                                document.getElementById('estado').value = c.state;
                                document.getElementById('latitude').value = c.lat.toFixed(2);
                                document.getElementById('longitude').value = c.lon.toFixed(2);
                                document.getElementById('timezone').value = c.tz.toFixed(1);
                                div.style.display = 'none';
                            }};
                            div.appendChild(item);
                        }});
                        div.style.display = 'block';
                    }}
                }} catch (e) {{
                    console.error(e);
                }}
            }});

            // Envio do formulário
            document.getElementById('mapForm').addEventListener('submit', async (e) => {{
                e.preventDefault();

                const dados = {{
                    nome: document.getElementById('nome').value,
                    dia: parseInt(document.getElementById('dia').value),
                    mes: parseInt(document.getElementById('mes').value),
                    ano: parseInt(document.getElementById('ano').value),
                    hora: parseInt(document.getElementById('hora').value),
                    minuto: parseInt(document.getElementById('minuto').value),
                    segundo: parseInt(document.getElementById('segundo').value),
                    latitude: parseFloat(document.getElementById('latitude').value),
                    longitude: parseFloat(document.getElementById('longitude').value),
                    timezone: parseFloat(document.getElementById('timezone').value),
                    cidade: document.getElementById('cidade').value,
                    estado: document.getElementById('estado').value,
                }};

                document.getElementById('loading').style.display = 'block';
                document.getElementById('resultado').style.display = 'none';

                try {{
                    const res = await fetch('/api/calcular', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify(dados)
                    }});

                    const json = await res.json();
                    document.getElementById('loading').style.display = 'none';

                    if (json.status === 'ok') {{
                        document.getElementById('textoResultado').textContent = json.relatorio;
                        document.getElementById('resultado').style.display = 'block';
                    }} else {{
                        alert('Erro: ' + json.msg);
                    }}
                }} catch (e) {{
                    document.getElementById('loading').style.display = 'none';
                    alert('Erro de conexão: ' + e.message);
                }}
            }});

            function fecharResultado() {{
                document.getElementById('resultado').style.display = 'none';
            }}
        </script>
    </body>
    </html>
    """
    return html


@app.route('/api/cidades')
def buscar_cidades():
    q = request.args.get('q', '').lower()
    try:
        cidmundo_path = os.path.join(os.path.dirname(__file__), 'CidMundo.txt')

        cidades = []
        if os.path.exists(cidmundo_path):
            with open(cidmundo_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    parts = line.split('|')
                    if len(parts) >= 9:
                        try:
                            city = parts[3].lower()
                            if q in city:
                                cidades.append({
                                    'city': parts[3],
                                    'state': parts[2],
                                    'country': parts[1],
                                    'lat': float(parts[4]),
                                    'lon': float(parts[5]),
                                    'tz': float(parts[8])
                                })
                                if len(cidades) >= 20:
                                    break
                        except:
                            pass

        return jsonify(cidades)
    except Exception as e:
        return jsonify({'erro': str(e)}), 400


@app.route('/api/calcular', methods=['POST'])
def calcular():
    try:
        dados = request.json

        mapa = MapaAstral(
            nome_mapa=dados.get('nome', 'Mapa'),
            dia=int(dados['dia']),
            mes=int(dados['mes']),
            ano=int(dados['ano']),
            hora=int(dados['hora']),
            minuto=int(dados['minuto']),
            segundo=int(dados['segundo']),
            latitude_dec=float(dados['latitude']),
            longitude_dec=float(dados['longitude']),
            timezone_horas=float(dados['timezone']),
            cidade=dados.get('cidade', ''),
            estado=dados.get('estado', ''),
            pais=dados.get('pais', 'Brasil')
        )

        relatorio = mapa.gerar_relatorio()

        return jsonify({
            'status': 'ok',
            'relatorio': relatorio,
            'planetas_count': len(mapa.planetas),
            'aspectos_count': len(mapa.aspectos_natais),
            'transitos_count': len(mapa.transitos)
        })
    except Exception as e:
        return jsonify({'status': 'erro', 'msg': str(e)}), 400


if __name__ == '__main__':
    app.run(debug=True)