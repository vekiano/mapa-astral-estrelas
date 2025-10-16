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


def buscar_mudanca_signo_exata(jd1, jd2, planeta):
    for _ in range(20):
        jd_meio = (jd1 + jd2) / 2
        lon1 = calcular_posicao_planeta(jd1, planeta)
        lon2 = calcular_posicao_planeta(jd_meio, planeta)
        lon3 = calcular_posicao_planeta(jd2, planeta)

        sig1 = int(lon1 / 30.0) % 12
        sig2 = int(lon2 / 30.0) % 12
        sig3 = int(lon3 / 30.0) % 12

        if sig2 != sig1:
            jd2 = jd_meio
        else:
            jd1 = jd_meio
    return (jd1 + jd2) / 2


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


@dataclass
class EventoAstral:
    jd_exato: float
    tipo: str
    descricao: str

    def __lt__(self, other):
        return self.jd_exato < other.jd_exato


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
        self.eventos = []

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
        self.eventos.clear()

        dt_inicio = self.dt_utc - timedelta(days=dias_margem)
        dt_fim = self.dt_utc + timedelta(days=dias_margem)
        jd_inicio = dt_to_jd_utc(dt_inicio)
        jd_fim = dt_to_jd_utc(dt_fim)

        # Aspectos
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

                        gap_atual = abs(diff_atual - aspecto_deg)
                        gap_prox = abs(diff_prox - aspecto_deg)

                        if min(gap_atual, gap_prox) < orbe:
                            trans = Transito(jd_atual, p1, p2, aspecto_deg, pos1_atual, pos2_atual,
                                             min(gap_atual, gap_prox), 'aspecto')
                            if trans not in self.transitos:
                                self.transitos.append(trans)
                        jd_atual = jd_prox

        # Mudanças de signo
        for nome, code in PLANETAS.items():
            jd_atual = jd_inicio
            signo_anterior = None
            while jd_atual < jd_fim:
                lon = calcular_posicao_planeta(jd_atual, code)
                signo_atual = int(lon / 30.0) % 12

                if signo_anterior is not None and signo_atual != signo_anterior:
                    jd_mudanca = buscar_mudanca_signo_exata(jd_atual - 0.1, jd_atual, code)
                    if jd_inicio <= jd_mudanca <= jd_fim:
                        descricao = f"{nome} entra em {SIGNOS[signo_atual]}"
                        self.eventos.append(EventoAstral(jd_mudanca, 'entrada_signo', descricao))

                signo_anterior = signo_atual
                jd_atual += 0.1

        # VOC da Lua
        entrada_lua = [e for e in self.eventos if 'LUA' in e.descricao and 'entra' in e.descricao]
        for entrada in entrada_lua:
            aspectos_antes = [t for t in self.transitos if t.planeta1 == swe.MOON or t.planeta2 == swe.MOON]
            aspectos_antes = [t for t in aspectos_antes if t.jd_exato < entrada.jd_exato]

            if aspectos_antes:
                ultimo = max(aspectos_antes, key=lambda x: x.jd_exato)
                jd_voc_inicio = ultimo.jd_exato + 1 / 86400.0
                jd_voc_fim = entrada.jd_exato
                duracao_dias = jd_voc_fim - jd_voc_inicio

                horas = int(duracao_dias * 24)
                minutos = int((duracao_dias * 24 - horas) * 60)

                lon_antes = calcular_posicao_planeta(jd_voc_inicio, swe.MOON)
                signo_saida = SIGNOS[int(lon_antes / 30.0) % 12]
                signo_entrada = entrada.descricao.split()[-1]

                descricao = f"LUA Fora de Curso {horas:02d}:{minutos:02d} até entrar em {signo_entrada}"
                self.eventos.append(EventoAstral(jd_voc_inicio, 'voc', descricao))

        # Adicionar transitos aos eventos
        for trans in self.transitos:
            p1_nome = PLANETA_REV.get(trans.planeta1, 'P1')
            p2_nome = PLANETA_REV.get(trans.planeta2, 'P2')

            asp_cod = None
            for cod, (alvo, _) in ASPECTOS.items():
                if abs(trans.aspecto - alvo) < 0.1:
                    asp_cod = cod
                    break

            sig1, pos1 = graus_para_signo_posicao(trans.pos_planeta1)
            sig2, pos2 = graus_para_signo_posicao(trans.pos_planeta2)

            descricao = f"[{p1_nome} {asp_cod} {p2_nome}] - {pos1} {sig1} / {pos2} {sig2}"
            self.eventos.append(EventoAstral(trans.jd_exato, 'aspecto', descricao))

        self.eventos.sort()

    def gerar_relatorio(self):
        self.calcular_planetas()
        self.calcular_casas()
        self.calcular_aspectos()
        self.calcular_transitos()

        rel = []
        rel.append("=" * 100)
        rel.append(self.nome_mapa or "MAPA ASTRAL")
        rel.append("=" * 100)
        rel.append(
            f"Data: {self.dia:02d}/{self.mes:02d}/{self.ano}  Hora: {self.hora:02d}:{self.minuto:02d}:{self.segundo:02d} (UTC {self.timezone_horas:+.1f}h)")
        if self.cidade or self.estado or self.pais:
            rel.append(f"Local: {self.cidade} / {self.estado} / {self.pais}")
        rel.append(f"Lat: {self.latitude:.6f}°  Lon: {self.longitude:.6f}°")
        rel.append("=" * 100)

        rel.append("\nPLANETAS:")
        rel.append("-" * 100)
        for nome in PLANETAS.keys():
            if nome in self.planetas:
                c = self.planetas[nome]
                rel.append(f"{nome:3s} [{c.pos_str} {c.signo}] {c.mov}")

        rel.append("\nCASAS:")
        rel.append("-" * 100)
        for num in range(1, 13):
            c = self.casas[num]
            rel.append(f"Casa {num:2d}: {c['posicao']} {c['signo']}")

        rel.append(f"\nASPECTOS ({len(self.aspectos_natais)}):")
        rel.append("-" * 100)
        for asp in sorted(self.aspectos_natais, key=lambda x: x['orbe']):
            linha = f"{asp['p1']:3s} [{asp['pos1']} {asp['sig1']}] {asp['cod']} {asp['p2']:3s} [{asp['pos2']} {asp['sig2']}] - Orbe: {asp['orbe']:.2f}°"
            rel.append(linha)

        if self.eventos:
            rel.append(f"\nTRÂNSITOS, ENTRADAS E VOC ({len(self.eventos)}):")
            rel.append("-" * 100)
            for evt in self.eventos:
                dt_evento = jd_para_datetime(evt.jd_exato, self.timezone_horas)
                dt_str = dt_evento.strftime('%d/%m/%Y %H:%M:%S')
                rel.append(f"{dt_str} - {evt.descricao}")

        rel.append("\n" + "=" * 100)
        return "\n".join(rel)


# ROTAS
@app.route('/')
def index():
    now = datetime.now()
    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mapa Astral</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;padding:20px}}
.container{{max-width:700px;margin:0 auto;background:white;border-radius:12px;padding:30px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}}h1{{text-align:center;color:#333;margin-bottom:20px}}
fieldset{{border:1px solid #ddd;border-radius:8px;padding:15px;margin-bottom:20px}}legend{{padding:0 10px;color:#667eea;font-weight:bold}}
input,select{{padding:8px;margin:5px 0;border:1px solid #ddd;border-radius:4px;font-size:12px}}
.row{{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:5px;margin-bottom:10px}}
.row3{{display:grid;grid-template-columns:80px 80px 80px 50px;gap:5px;margin-bottom:10px}}
.row2{{display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:8px;margin-bottom:10px}}
button{{width:100%;padding:10px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:4px;cursor:pointer;font-weight:bold}}
button:hover{{transform:translateY(-2px)}}
.resultado{{margin-top:20px;padding:15px;background:#f0f9ff;border-radius:8px;display:none;max-height:400px;overflow-y:auto}}
.resultado pre{{font-family:monospace;font-size:11px;color:#1e3a8a}}
.loading{{display:none;text-align:center;color:#667eea;font-weight:bold}}
#modal{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:1000;align-items:center;justify-content:center}}
#modal>div{{background:white;padding:20px;border-radius:8px;width:90%;max-width:400px}}
#cidades-list{{max-height:200px;overflow-y:auto;border:1px solid #ddd;border-radius:4px}}
.cidade-item{{padding:8px;border-bottom:1px solid #eee;cursor:pointer}}
.cidade-item:hover{{background:#f0f9ff}}
</style>
</head>
<body><div class="container"><h1>🌙 Mapa Astral Online</h1>
<form id="f">
<fieldset><legend>Identificação</legend>
<input type="text" id="nome" value="Mapa do Momento" required>
<div class="row">
<input type="number" id="dia" min="1" max="31" value="{now.day}" required>
<input type="number" id="mes" min="1" max="12" value="{now.month}" required>
<input type="number" id="ano" value="{now.year}" required>
<div style="border:1px solid #ddd;border-radius:4px;padding:8px;text-align:center;background:#f9f9f9">{now.day:02d}/{now.month:02d}/{now.year}</div>
</div>
<div class="row">
<input type="number" id="hora" min="0" max="23" value="{now.hour}" required>
<input type="number" id="minuto" min="0" max="59" value="{now.minute}" required>
<input type="number" id="segundo" min="0" max="59" value="{now.second}" required>
<div style="border:1px solid #ddd;border-radius:4px;padding:8px;text-align:center;background:#f9f9f9">{now.hour:02d}:{now.minute:02d}:{now.second:02d}</div>
</div>
</fieldset>
<fieldset><legend>Localização</legend>
<div class="row2">
<input type="text" id="cidade" value="Brasília" required>
<input type="text" id="estado" value="DF" required>
<input type="text" id="pais" value="Brasil" required>
<button type="button" onclick="abrirBusca()">Buscar</button>
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
<div class="row2" style="grid-template-columns:100px 1fr">
<input type="number" id="tz" step="0.5" value="-3" required>
<select><option>W</option><option>E</option></select>
</div>
<select style="width:100%"><option>Regiomontanus</option></select>
</fieldset>
<button type="submit">CALCULAR</button>
</form>
<div class="loading" id="load">Calculando...</div>
<div class="resultado" id="res"><pre id="txt"></pre></div>
</div>

<div id="modal"><div>
<h3>Buscar Cidade</h3>
<input type="text" id="search" placeholder="Digite a cidade..." style="width:100%;padding:10px;margin:10px 0;border:1px solid #ddd;border-radius:4px">
<div id="cidades-list"></div>
<button onclick="document.getElementById('modal').style.display='none'" style="margin-top:10px">Fechar</button>
</div></div>

<script>
function dmsToDecimal(g,m,s,h){{let d=Math.abs(g)+Math.abs(m)/60+Math.abs(s)/3600;return(h=='S'||h=='W')?-d:d}}
function abrirBusca(){{document.getElementById('modal').style.display='flex';document.getElementById('search').focus()}}
document.getElementById('search').addEventListener('input',async e=>{{
  let q=e.target.value;if(q.length<2){{document.getElementById('cidades-list').innerHTML='';return}}
  let r=await fetch('/api/cidades?q='+q);let c=await r.json();
  document.getElementById('cidades-list').innerHTML='';
  c.forEach(d=>{{
    let div=document.createElement('div');div.className='cidade-item';
    div.textContent=d.city+', '+d.state+' - '+d.country;
    div.onclick=()=>{{
      document.getElementById('cidade').value=d.city;
      document.getElementById('estado').value=d.state;
      document.getElementById('pais').value=d.country;
      let latD=Math.abs(d.lat),latG=Math.floor(latD),latM=Math.floor((latD-latG)*60),latS=Math.round(((latD-latG)*60-latM)*60);
      document.getElementById('latg').value=latG;
      document.getElementById('latm').value=latM;
      document.getElementById('lats').value=latS;
      document.getElementById('lath').value=(d.lat<0?'S':'N');
      let lonD=Math.abs(d.lon),lonG=Math.floor(lonD),lonM=Math.floor((lonD-lonG)*60),lonS=Math.round(((lonD-lonG)*60-lonM)*60);
      document.getElementById('long').value=lonG;
      document.getElementById('lonm').value=lonM;
      document.getElementById('lons').value=lonS;
      document.getElementById('lonh').value=(d.lon<0?'W':'E');
      document.getElementById('tz').value=d.tz;
      document.getElementById('modal').style.display='none';
    }};
    document.getElementById('cidades-list').appendChild(div);
  }})
}});
document.getElementById('f').addEventListener('submit',async e=>{{
  e.preventDefault();
  let lat=dmsToDecimal(parseInt(document.getElementById('latg').value),parseInt(document.getElementById('latm').value),parseInt(document.getElementById('lats').value),document.getElementById('lath').value);
  let lon=dmsToDecimal(parseInt(document.getElementById('long').value),parseInt(document.getElementById('lonm').value),parseInt(document.getElementById('lons').value),document.getElementById('lonh').value);
  let dados={{nome:document.getElementById('nome').value,dia:parseInt(document.getElementById('dia').value),mes:parseInt(document.getElementById('mes').value),ano:parseInt(document.getElementById('ano').value),hora:parseInt(document.getElementById('hora').value),minuto:parseInt(document.getElementById('minuto').value),segundo:parseInt(document.getElementById('segundo').value),latitude:lat,longitude:lon,timezone:parseFloat(document.getElementById('tz').value),cidade:document.getElementById('cidade').value,estado:document.getElementById('estado').value,pais:document.getElementById('pais').value}};
  document.getElementById('load').style.display='block';document.getElementById('res').style.display='none';
  let res=await fetch('/api/calcular',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(dados)}});
  let j=await res.json();document.getElementById('load').style.display='none';
  if(j.status=='ok'){{document.getElementById('txt').textContent=j.relatorio;document.getElementById('res').style.display='block'}}
  else alert('Erro: '+j.msg);
}});
</script>
</body></html>'''


@app.route('/api/cidades')
def cidades():
    q = request.args.get('q', '').lower()
    cidmundo = os.path.join(os.path.dirname(__file__), 'CidMundo.txt')
    result = []
    if os.path.exists(cidmundo):
        try:
            with open(cidmundo, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    p = line.split('|')
                    if len(p) >= 9:
                        try:
                            city = p[3].lower()
                            if q in city:
                                result.append({
                                    'city': p[3],
                                    'state': p[2],
                                    'country': p[1],
                                    'lat': float(p[4]),
                                    'lon': float(p[5]),
                                    'tz': float(p[8])
                                })
                                if len(result) >= 20:
                                    break
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