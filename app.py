# -*- coding: utf-8 -*-
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from flask import Flask, request, jsonify

try:
    import swisseph as swe
except:
    pass

app = Flask(__name__)

# CONSTANTES
ASPECTOS = {
    'CJN': (0.0, 8.0), 'OPO': (180.0, 8.0), 'TRI': (120.0, 8.0),
    'SQR': (90.0, 6.0), 'SXT': (60.0, 6.0), 'QCX': (150.0, 3.0),
    'SSQ': (45.0, 2.0), 'SQQ': (135.0, 2.0),
}
ORBES_PADRAO = {0.0: 8.0, 45.0: 2.0, 60.0: 6.0, 90.0: 6.0, 120.0: 8.0, 135.0: 2.0, 150.0: 3.0, 180.0: 8.0}
SIGNOS = ['AR', 'TA', 'GE', 'CA', 'LE', 'VI', 'LI', 'SC', 'SG', 'CP', 'AQ', 'PI']
PLANETAS = {
    'SOL': swe.SUN, 'LUA': swe.MOON, 'MER': swe.MERCURY, 'VEN': swe.VENUS,
    'MAR': swe.MARS, 'JUP': swe.JUPITER, 'SAT': swe.SATURN, 'URA': swe.URANUS,
    'NET': swe.NEPTUNE, 'PLU': swe.PLUTO, 'TNN': swe.TRUE_NODE,
}
PLANETA_REV = {v: k for k, v in PLANETAS.items()}


# FUNÇÕES
def graus_para_dms(graus):
    graus = graus % 360.0
    g = int(graus)
    m = int((graus - g) * 60)
    s = int(((graus - g) * 60 - m) * 60)
    return f"{g:02d}°{m:02d}'{s:02d}\""


def graus_para_signo_posicao(graus):
    graus = graus % 360.0
    idx = int(graus / 30.0)
    pos_no_signo = graus % 30.0
    return SIGNOS[idx], graus_para_dms(pos_no_signo)


def angular_difference(a, b):
    d = abs((a % 360.0) - (b % 360.0))
    return d if d <= 180.0 else 360.0 - d


def dt_to_jd_utc(dt_utc):
    frac = (dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0)
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, frac, 1)


def jd_para_datetime(jd, tz_offset=0.0):
    year, month, day, hour = swe.revjul(jd + tz_offset / 24.0)
    hour_int = int(hour)
    minute = int((hour - hour_int) * 60)
    second = int(((hour - hour_int) * 60 - minute) * 60)
    return datetime(year, month, day, hour_int, minute, second)


def calcular_posicao_planeta(jd, planeta):
    pos, _ = swe.calc_ut(jd, planeta)
    return float(pos[0]) % 360.0


@dataclass
class Corpo:
    nome: str
    lon: float
    lat: float
    vel: float
    mov: str
    signo: str
    pos_str: str


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


class MapaAstral:
    def __init__(self, nome_mapa, dia, mes, ano, hora, minuto, segundo,
                 latitude_dec, longitude_dec, timezone_horas, cidade='', estado='', pais=''):
        self.nome_mapa = nome_mapa.strip()
        self.dia, self.mes, self.ano = dia, mes, ano
        self.hora, self.minuto, self.segundo = hora, minuto, segundo
        self.latitude, self.longitude = latitude_dec, longitude_dec
        self.timezone_horas = timezone_horas
        self.cidade, self.estado, self.pais = cidade, estado, pais

        self.dt_local = datetime(ano, mes, dia, hora, minuto, segundo)
        self.dt_utc = self.dt_local - timedelta(hours=timezone_horas)
        self.jd = dt_to_jd_utc(self.dt_utc)

        self.planetas = {}
        self.casas = {}
        self.aspectos_natais = []
        self.transitos = []

        swe.set_ephe_path(None)

    def calcular_planetas(self):
        self.planetas.clear()
        for nome, code in PLANETAS.items():
            pos, _ = swe.calc_ut(self.jd, code)
            lon, lat, lon_speed = float(pos[0]), float(pos[1]), float(pos[3])
            mov = 'DIR' if lon_speed >= 0 else 'RET'
            signo, pos_str = graus_para_signo_posicao(lon)
            self.planetas[nome] = Corpo(nome, lon, lat, lon_speed, mov, signo, pos_str)

    def calcular_casas(self):
        self.casas.clear()
        casas, _ = swe.houses(self.jd, self.latitude, self.longitude, b'R')
        for i in range(12):
            lon = float(casas[i])
            s, p = graus_para_signo_posicao(lon)
            self.casas[i + 1] = {'longitude': lon, 'signo': s, 'posicao': p}

    def calcular_aspectos(self):
        self.aspectos_natais.clear()
        nomes = list(PLANETAS.keys())
        for i, p1_nome in enumerate(nomes):
            for p2_nome in nomes[i + 1:]:
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

    def calcular_transitos(self, dias_margem=2):
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
                    intervalo = 0.1
                    jd_atual = jd_inicio
                    while jd_atual < jd_fim:
                        jd_prox = min(jd_atual + intervalo, jd_fim)
                        pos1_atual = calcular_posicao_planeta(jd_atual, p1)
                        pos2_atual = calcular_posicao_planeta(jd_atual, p2)
                        pos1_prox = calcular_posicao_planeta(jd_prox, p1)
                        pos2_prox = calcular_posicao_planeta(jd_prox, p2)

                        diff_atual = angular_difference(pos1_atual, pos2_atual)
                        diff_prox = angular_difference(pos1_prox, pos2_prox)

                        if abs(diff_atual - aspecto_deg) < orbe or abs(diff_prox - aspecto_deg) < orbe:
                            trans = Transito(jd_atual, p1, p2, aspecto_deg, pos1_atual, pos2_atual, 0.01, 'aspecto')
                            self.transitos.append(trans)
                        jd_atual = jd_prox

        self.transitos.sort(key=lambda x: x.jd_exato)

    def gerar_relatorio(self):
        self.calcular_planetas()
        self.calcular_casas()
        self.calcular_aspectos()
        self.calcular_transitos()

        rel = []
        rel.append("=" * 80)
        rel.append(self.nome_mapa or "MAPA ASTRAL")
        rel.append("=" * 80)
        rel.append(
            f"Data: {self.dia:02d}/{self.mes:02d}/{self.ano}  Hora: {self.hora:02d}:{self.minuto:02d}:{self.segundo:02d}")
        if self.cidade or self.estado or self.pais:
            rel.append(f"Local: {self.cidade} / {self.estado} / {self.pais}")
        rel.append(f"Lat: {self.latitude:.6f}°  Lon: {self.longitude:.6f}°  UTC: {self.timezone_horas:+.1f}h")
        rel.append("=" * 80)

        rel.append("\nPLANETAS:")
        rel.append("-" * 80)
        for nome in PLANETAS.keys():
            if nome in self.planetas:
                c = self.planetas[nome]
                rel.append(f"{nome:3s} [{c.pos_str} {c.signo}] {c.mov}")

        rel.append("\nCASAS ASTROLÓGICAS:")
        rel.append("-" * 80)
        for num in range(1, 13):
            c = self.casas[num]
            rel.append(f"Casa {num:2d}: {c['posicao']} {c['signo']}")

        rel.append(f"\nASPECTOS ({len(self.aspectos_natais)}):")
        rel.append("-" * 80)
        for asp in sorted(self.aspectos_natais, key=lambda x: x['orbe']):
            linha = f"{asp['p1']:3s} [{asp['pos1']} {asp['sig1']}] {asp['cod']} {asp['p2']:3s} [{asp['pos2']} {asp['sig2']}] - Orbe: {asp['orbe']:.2f}°"
            rel.append(linha)

        rel.append("\n" + "=" * 80)
        return "\n".join(rel)


# ROTAS
@app.route('/')
def index():
    now = datetime.now()
    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Mapa Astral</title>
    <style>
        * {{margin:0; padding:0; box-sizing:border-box;}}
        body {{font-family:Arial,sans-serif; background:linear-gradient(135deg,#667eea,#764ba2); min-height:100vh; padding:20px;}}
        .container {{max-width:700px; margin:0 auto; background:white; border-radius:12px; padding:30px; box-shadow:0 20px 60px rgba(0,0,0,0.3);}}
        h1 {{text-align:center; color:#333; margin-bottom:20px;}}
        fieldset {{border:1px solid #ddd; border-radius:8px; padding:15px; margin-bottom:20px;}}
        legend {{padding:0 10px; color:#667eea; font-weight:bold;}}
        input,select {{padding:8px; margin:5px 0; border:1px solid #ddd; border-radius:4px; font-size:12px;}}
        .row {{display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:5px; margin-bottom:10px;}}
        .row3 {{display:grid; grid-template-columns:80px 80px 80px 50px; gap:5px; margin-bottom:10px;}}
        .row2 {{display:grid; grid-template-columns:1fr 1fr 1fr auto; gap:8px; margin-bottom:10px;}}
        button {{width:100%; padding:10px; background:linear-gradient(135deg,#667eea,#764ba2); color:white; border:none; border-radius:4px; cursor:pointer; font-weight:bold;}}
        button:hover {{transform:translateY(-2px);}}
        .resultado {{margin-top:20px; padding:15px; background:#f0f9ff; border-radius:8px; display:none; max-height:400px; overflow-y:auto;}}
        .resultado pre {{font-family:monospace; font-size:11px; color:#1e3a8a;}}
        .loading {{display:none; text-align:center; color:#667eea; font-weight:bold;}}
    </style>
</head>
<body>
    <div class="container">
        <h1>🌙 Mapa Astral Online</h1>
        <form id="f">
            <fieldset>
                <legend>Identificação</legend>
                <input type="text" id="nome" value="Mapa do Momento" required>
                <div class="row">
                    <input type="number" id="dia" min="1" max="31" value="{now.day}" required>
                    <input type="number" id="mes" min="1" max="12" value="{now.month}" required>
                    <input type="number" id="ano" value="{now.year}" required>
                    <div style="border:1px solid #ddd; border-radius:4px; padding:8px; text-align:center; background:#f9f9f9;">{now.day:02d}/{now.month:02d}/{now.year}</div>
                </div>
                <div class="row">
                    <input type="number" id="hora" min="0" max="23" value="{now.hour}" required>
                    <input type="number" id="minuto" min="0" max="59" value="{now.minute}" required>
                    <input type="number" id="segundo" min="0" max="59" value="{now.second}" required>
                    <div style="border:1px solid #ddd; border-radius:4px; padding:8px; text-align:center; background:#f9f9f9;">{now.hour:02d}:{now.minute:02d}:{now.second:02d}</div>
                </div>
            </fieldset>
            <fieldset>
                <legend>Localização</legend>
                <div class="row2">
                    <input type="text" id="cidade" value="Brasília" required>
                    <input type="text" id="estado" value="DF" required>
                    <input type="text" id="pais" value="Brasil" required>
                    <button type="button" onclick="alert('Busca em desenvolvimento')">Buscar</button>
                </div>
                <div class="row3">
                    <input type="number" id="latg" min="0" max="90" value="15" required>
                    <input type="number" id="latm" min="0" max="59" value="46" required>
                    <input type="number" id="lats" min="0" max="59" value="12" required>
                    <select id="lath"><option>N</option><option selected>S</option></select>
                </div>
                <div class="row3">
                    <input type="number" id="long" min="0" max="180" value="47" required>
                    <input type="number" id="lonm" min="0" max="59" value="55" required>
                    <input type="number" id="lons" min="0" max="59" value="12" required>
                    <select id="lonh"><option>E</option><option selected>W</option></select>
                </div>
                <div class="row2" style="grid-template-columns:100px 1fr;">
                    <input type="number" id="tz" step="0.5" value="-3" required>
                    <select><option>W</option><option>E</option></select>
                </div>
                <select style="width:100%;"><option>Regiomontanus</option></select>
            </fieldset>
            <button type="submit">CALCULAR</button>
        </form>
        <div class="loading" id="load">Calculando...</div>
        <div class="resultado" id="res"><pre id="txt"></pre></div>
    </div>
    <script>
        function dmsToDecimal(g,m,s,h){{let d=Math.abs(g)+Math.abs(m)/60+Math.abs(s)/3600;if(h=='S'||h=='W')d=-d;return d;}}
        document.getElementById('f').addEventListener('submit',async e=>{{
            e.preventDefault();
            let lat=dmsToDecimal(parseInt(document.getElementById('latg').value),parseInt(document.getElementById('latm').value),parseInt(document.getElementById('lats').value),document.getElementById('lath').value);
            let lon=dmsToDecimal(parseInt(document.getElementById('long').value),parseInt(document.getElementById('lonm').value),parseInt(document.getElementById('lons').value),document.getElementById('lonh').value);
            let dados={{
                nome:document.getElementById('nome').value,
                dia:parseInt(document.getElementById('dia').value),
                mes:parseInt(document.getElementById('mes').value),
                ano:parseInt(document.getElementById('ano').value),
                hora:parseInt(document.getElementById('hora').value),
                minuto:parseInt(document.getElementById('minuto').value),
                segundo:parseInt(document.getElementById('segundo').value),
                latitude:lat,
                longitude:lon,
                timezone:parseFloat(document.getElementById('tz').value),
                cidade:document.getElementById('cidade').value,
                estado:document.getElementById('estado').value,
                pais:document.getElementById('pais').value
            }};
            document.getElementById('load').style.display='block';
            document.getElementById('res').style.display='none';
            let r=await fetch('/api/calcular',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(dados)}});
            let j=await r.json();
            document.getElementById('load').style.display='none';
            if(j.status=='ok'){{document.getElementById('txt').textContent=j.relatorio;document.getElementById('res').style.display='block';}}
            else alert('Erro: '+j.msg);
        }});
    </script>
</body>
</html>'''


@app.route('/api/cidades')
def cidades():
    q = request.args.get('q', '').lower()
    cidmundo = os.path.join(os.path.dirname(__file__), 'CidMundo.txt')
    result = []
    if os.path.exists(cidmundo):
        try:
            with open(cidmundo, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('#') or not line.strip(): continue
                    p = line.split('|')
                    if len(p) >= 9:
                        try:
                            if q in p[3].lower():
                                result.append({'city': p[3], 'state': p[2], 'country': p[1], 'lat': float(p[4]),
                                               'lon': float(p[5]), 'tz': float(p[8])})
                                if len(result) >= 20: break
                        except:
                            pass
        except:
            pass
    return jsonify(result)


@app.route('/api/calcular', methods=['POST'])
def calcular():
    try:
        d = request.json
        m = MapaAstral(d.get('nome', 'Mapa'), int(d['dia']), int(d['mes']), int(d['ano']),
                       int(d['hora']), int(d['minuto']), int(d['segundo']),
                       float(d['latitude']), float(d['longitude']), float(d['timezone']),
                       d.get('cidade', ''), d.get('estado', ''), d.get('pais', ''))
        return jsonify({'status': 'ok', 'relatorio': m.gerar_relatorio()})
    except Exception as e:
        return jsonify({'status': 'erro', 'msg': str(e)}), 400


if __name__ == '__main__':
    app.run(debug=True)