# -*- coding: utf-8 -*-
"""
Mapa Astral Online - Vercel
Sem interface gráfica, apenas API Flask
"""

import os
import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

from flask import Flask, request, jsonify, send_from_directory

try:
    import swisseph as swe
except:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')

app = Flask(__name__, static_folder=PUBLIC_DIR, static_url_path='')

@app.route('/')
def index():
    return send_from_directory(PUBLIC_DIR, 'index.html')

# ========== CONSTANTES ==========

ASPECTOS = {
    'CJN': (0.0, 8.0),
    'OPO': (180.0, 8.0),
    'TRI': (120.0, 8.0),
    'SQR': (90.0, 6.0),
    'SXT': (60.0, 6.0),
    'QCX': (150.0, 3.0),
    'SSQ': (45.0, 2.0),
    'SQQ': (135.0, 2.0),
}

ORBES_PADRAO = {
    0.0: 8.0, 45.0: 2.0, 60.0: 6.0, 90.0: 6.0, 120.0: 8.0,
    135.0: 2.0, 150.0: 3.0, 180.0: 8.0
}

SIGNOS = ['AR', 'TA', 'GE', 'CA', 'LE', 'VI', 'LI', 'SC', 'SG', 'CP', 'AQ', 'PI']

PLANETAS = {
    'SOL': swe.SUN,
    'LUA': swe.MOON,
    'MER': swe.MERCURY,
    'VEN': swe.VENUS,
    'MAR': swe.MARS,
    'JUP': swe.JUPITER,
    'SAT': swe.SATURN,
    'URA': swe.URANUS,
    'NET': swe.NEPTUNE,
    'PLU': swe.PLUTO,
    'TNN': swe.TRUE_NODE,
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
                            'p1': p1_nome,
                            'p2': p2_nome,
                            'cod': cod,
                            'orbe': gap,
                            'pos1': pos1,
                            'sig1': sig1,
                            'pos2': pos2,
                            'sig2': sig2,
                        })

    def gerar_relatorio(self) -> str:
        self.calcular_planetas()
        self.calcular_casas()
        self.calcular_aspectos()

        rel = []
        rel.append("=" * 80)
        rel.append(self.nome_mapa or "MAPA ASTRAL")
        rel.append("=" * 80)
        rel.append(
            f"Data: {self.dia:02d}/{self.mes:02d}/{self.ano}  Hora: {self.hora:02d}:{self.minuto:02d}:{self.segundo:02d} (UTC {self.timezone_horas:+.2f}h)")
        if any([self.cidade, self.estado, self.pais]):
            rel.append(f"Local: {self.cidade} / {self.estado} / {self.pais}")
        rel.append(f"Latitude: {self.latitude:.6f}°  Longitude: {self.longitude:.6f}°")
        rel.append("=" * 80)
        rel.append("")

        rel.append("PLANETAS:")
        rel.append("-" * 80)
        for nome in PLANETAS.keys():
            if nome in self.planetas:
                c = self.planetas[nome]
                rel.append(f"{nome:3s} [{c.pos_str} {c.signo}] {c.mov}")

        rel.append("")
        rel.append("CASAS ASTROLÓGICAS:")
        rel.append("-" * 80)
        for num in range(1, 13):
            c = self.casas[num]
            rel.append(f"Casa {num:2d}: {c['posicao']} {c['signo']}")

        rel.append("")
        rel.append(f"ASPECTOS ({len(self.aspectos_natais)}):")
        rel.append("-" * 80)
        for asp in sorted(self.aspectos_natais, key=lambda x: x['orbe']):
            linha = f"{asp['p1']:3s} [{asp['pos1']} {asp['sig1']}] {asp['cod']} {asp['p2']:3s} [{asp['pos2']} {asp['sig2']}] - Orbe: {asp['orbe']:.2f}°"
            rel.append(linha)

        rel.append("")
        rel.append("=" * 80)
        return "\n".join(rel)


# ========== ROTAS ==========

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')


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
            pais=dados.get('pais', '')
        )

        relatorio = mapa.gerar_relatorio()

        return jsonify({
            'status': 'ok',
            'relatorio': relatorio,
            'planetas_count': len(mapa.planetas),
            'aspectos_count': len(mapa.aspectos_natais)
        })
    except Exception as e:
        return jsonify({'status': 'erro', 'msg': str(e)}), 400


if __name__ == '__main__':
    app.run(debug=True)