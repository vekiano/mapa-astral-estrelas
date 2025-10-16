# -*- coding: utf-8 -*-
"""
Mapa Astral com Trânsitos (mapa_ah) - Versão Completa com UI
Integra: Entrada de dados + Cálculo de Mapa + Cálculo de Trânsitos (metodologia transito_delph)
Com deduplicação de trânsitos, posições astrológicas, VOC da Lua e entradas de signos

Requisitos: pip install pyswisseph
Coloque CidMundo.txt na mesma pasta do script
"""

from __future__ import annotations
import os
import sys
import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

try:
    import swisseph as swe
except Exception as e:
    raise SystemExit("Este programa requer 'pyswisseph'. Instale com: pip install pyswisseph")


def get_resource_path(filename):
    """Encontra o caminho do arquivo, seja em desenvolvimento ou como executável"""
    if getattr(sys, 'frozen', False):
        # Rodando como executável
        base_path = sys._MEIPASS
    else:
        # Rodando como script Python
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, filename)

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

HOUSE_SYSTEMS = {
    'Placidus': b'P', 'Koch': b'K', 'Regiomontanus': b'R', 'Campanus': b'C',
    'Porphyry': b'O', 'Equal': b'E', 'Whole Sign': b'W', 'Alcabitius': b'B',
}


# ========== FUNÇÕES AUXILIARES ==========

def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


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


def dias_para_hms(dias: float) -> str:
    """Converte dias decimais em formato HH:MM:SS"""
    dias = abs(dias)
    horas = dias * 24
    h = int(horas)
    minutos = (horas - h) * 60
    m = int(minutos)
    segundos = int((minutos - m) * 60)
    return f"{h:02d}:{m:02d}:{segundos:02d}"


def dec_to_dms_components(value: float, is_lat: bool) -> Tuple[int, int, int, str]:
    sign = -1 if value < 0 else 1
    absval = abs(value)
    deg = int(absval)
    minutes_float = (absval - deg) * 60.0
    minutes = int(minutes_float)
    seconds = int(round((minutes_float - minutes) * 60.0))
    if seconds == 60: seconds = 0; minutes += 1
    if minutes == 60: minutes = 0; deg += 1
    hemi = ('S' if sign < 0 else 'N') if is_lat else ('W' if sign < 0 else 'E')
    return deg, minutes, seconds, hemi


def dms_to_decimal(deg: int, minutes: int, seconds: int, hemi: str, is_lat: bool) -> float:
    hemi = hemi.upper()
    value = abs(deg) + abs(minutes) / 60.0 + abs(seconds) / 3600.0
    if is_lat and hemi == 'S': value = -value
    if not is_lat and hemi == 'W': value = -value
    return value


def calcular_posicao_planeta(jd: float, planeta: int) -> float:
    pos, _ = swe.calc_ut(jd, planeta)
    return float(pos[0]) % 360.0


def calcular_declinacao_planeta(jd: float, planeta: int) -> float:
    eq, _ = swe.calc_ut(jd, planeta, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)
    return float(eq[1])


# ========== CLASSES DE DADOS ==========

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
class CityRow:
    country_code: str
    country: str
    state: str
    city: str
    lat: float
    lon: float
    tz_code: str
    tz_id: str
    utc_offset: float


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
    """Evento astral genérico (trânsito, VOC, entrada de signo, etc)"""
    jd_exato: float
    tipo: str  # 'aspecto', 'voc', 'entrada_signo', 'par', 'cpa'
    descricao: str

    def __lt__(self, other):
        return self.jd_exato < other.jd_exato


# ========== BUSCA DE TRÂNSITOS (Metodologia transito_delph) ==========

def determinar_intervalo(planeta1: int, planeta2: int) -> float:
    """Intervalo de busca baseado na velocidade dos planetas"""
    planeta_lento = max(planeta1, planeta2)
    intervalos = {
        swe.MOON: 0.01, swe.MERCURY: 0.05, swe.VENUS: 0.05, swe.SUN: 0.05,
        swe.MARS: 0.1, swe.JUPITER: 0.2, swe.SATURN: 0.5, swe.URANUS: 1.0,
        swe.NEPTUNE: 1.0, swe.PLUTO: 1.0, swe.TRUE_NODE: 0.5, swe.MEAN_NODE: 0.5,
    }
    return intervalos.get(planeta_lento, 0.5)


def buscar_transito_exato(jd_inicio: float, jd_fim: float, planeta1: int, planeta2: int,
                          angulo_aspecto: float, orbe: float) -> Tuple[float, float]:
    """Busca o momento exato de um trânsito"""
    NUM_SAMPLES = 12
    BISSECCOES_MAX = 6
    SECANTE_JUMP_MAX = 1.0
    DELTA_MIN = 1.0e-10
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

    jd = melhor_jd
    dx = (jd2 - jd1) / 4

    for _ in range(20):
        jd_ant = jd
        jd_prox = jd + dx
        orbe_ant = calcular_orbe_atual(jd_ant)
        orbe_prox = calcular_orbe_atual(jd_prox)

        if abs(orbe_prox - orbe_ant) < DELTA_MIN:
            break

        dx = -orbe_ant * (jd_prox - jd_ant) / (orbe_prox - orbe_ant)
        if abs(dx) > SECANTE_JUMP_MAX:
            dx = SECANTE_JUMP_MAX if dx > 0 else -SECANTE_JUMP_MAX

        jd = jd_ant + dx
        orbe = abs(calcular_orbe_atual(jd))

        if orbe < melhor_orbe:
            melhor_orbe = orbe
            melhor_jd = jd

        if orbe <= 0.001 or abs(dx) < 0.0001:
            return jd, orbe

    return melhor_jd, melhor_orbe if melhor_orbe <= orbe else (0, 999)


def buscar_mudanca_signo_exata(jd1: float, jd2: float, planeta: int, signo_saida: int) -> float:
    """Encontra o momento exato de mudança de signo usando bissecção"""
    BISSECCOES_MAX = 20
    DELTA_MIN = 1.0e-12

    def signo_atual(jd: float) -> int:
        lon = calcular_posicao_planeta(jd, planeta)
        return int(lon / 30.0) % 12

    for _ in range(BISSECCOES_MAX):
        jd_meio = (jd1 + jd2) / 2
        sig_meio = signo_atual(jd_meio)

        if sig_meio == signo_saida:
            jd1 = jd_meio
        else:
            jd2 = jd_meio

        if abs(jd2 - jd1) < DELTA_MIN:
            return jd_meio

    return (jd1 + jd2) / 2


# ========== NÚCLEO: MAPA ASTRAL ==========

class MapaAstral:
    def __init__(self, nome_mapa: str, dia, mes, ano, hora, minuto, segundo,
                 latitude_dec: float, longitude_dec: float, timezone_horas: float,
                 cidade: str = '', estado: str = '', pais: str = '',
                 house_system_label: str = 'Regiomontanus'):
        self.nome_mapa = nome_mapa.strip()
        self.dia, self.mes, self.ano = dia, mes, ano
        self.hora, self.minuto, self.segundo = hora, minuto, segundo
        self.latitude, self.longitude = latitude_dec, longitude_dec
        self.timezone_horas = timezone_horas
        self.cidade, self.estado, self.pais = cidade, estado, pais
        self.house_system_label = house_system_label
        self.hsys = HOUSE_SYSTEMS.get(house_system_label, b'R')

        self.dt_local = datetime(ano, mes, dia, hora, minuto, segundo)
        self.dt_utc = self.dt_local - timedelta(hours=timezone_horas)
        self.jd = dt_to_jd_utc(self.dt_utc)

        self.planetas: Dict[str, Corpo] = {}
        self.casas: Dict[int, Dict] = {}
        self.transitos: List[Transito] = []
        self.mudancas_signo: List[EventoAstral] = []
        self.voc_periodos: List[Dict] = []
        self.eventos_astral: List[EventoAstral] = []
        self.aspectos_natais: List[Dict] = []

        swe.set_ephe_path(None)

    def _houses(self, jd: float):
        return swe.houses(jd, self.latitude, self.longitude, self.hsys)

    def calcular_planetas(self) -> None:
        self.planetas.clear()
        for nome, code in PLANETAS.items():
            pos, _ = swe.calc_ut(self.jd, code)
            lon, lat, lon_speed = float(pos[0]), float(pos[1]), float(pos[3])
            mov = 'dir' if lon_speed >= 0 else 'ret'
            signo, pos_str = graus_para_signo_posicao(lon)
            eq, _ = swe.calc_ut(self.jd, code, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)
            decl = float(eq[1])
            self.planetas[nome] = Corpo(nome, lon, lat, lon_speed, mov, signo, pos_str, decl)

        casas, ascmc = self._houses(self.jd)
        asc_lon = float(ascmc[0]);
        mc_lon = float(ascmc[1])
        s_asc, p_asc = graus_para_signo_posicao(asc_lon)
        s_mc, p_mc = graus_para_signo_posicao(mc_lon)

        ecl, _ = swe.calc_ut(self.jd, swe.ECL_NUT)
        eps = math.radians(float(ecl[0]))
        asc_decl = math.degrees(math.asin(math.sin(eps) * math.sin(math.radians(asc_lon))))
        mc_decl = math.degrees(math.asin(math.sin(eps) * math.sin(math.radians(mc_lon))))

        self.planetas['ASC'] = Corpo('ASC', asc_lon, 0.0, 0.0, 'dir', s_asc, p_asc, asc_decl)
        self.planetas['MC'] = Corpo('MC', mc_lon, 0.0, 0.0, 'dir', s_mc, p_mc, mc_decl)

    def calcular_casas(self) -> None:
        self.casas.clear()
        casas, _ = self._houses(self.jd)
        for i in range(12):
            num = i + 1
            lon = float(casas[i])
            s, p = graus_para_signo_posicao(lon)
            self.casas[num] = {'longitude': lon, 'signo': s, 'posicao': p}

    def calcular_aspectos(self) -> None:
        """Calcula aspectos entre planetas natais com posições astrológicas"""
        self.aspectos_natais.clear()
        nomes = list(PLANETAS.keys()) + ['ASC', 'MC']

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
                            'dif': dif,
                            'orbe': gap,
                            'pos1': pos1,
                            'sig1': sig1,
                            'pos2': pos2,
                            'sig2': sig2,
                        })

    def _deduplicate_transitos(self, janela_tempo: float = 0.15) -> None:
        """Remove duplicatas de trânsitos mantendo apenas o com menor orbe"""
        if not self.transitos:
            return

        grupos = {}
        for trans in self.transitos:
            if trans.tipo in ['PAR', 'CPA']:
                asp_key = trans.tipo
            else:
                asp_key = round(trans.aspecto, 1)

            chave = (trans.planeta1, trans.planeta2, asp_key)
            if chave not in grupos:
                grupos[chave] = []
            grupos[chave].append(trans)

        transitos_filtrados = []

        for chave, transitos_grupo in grupos.items():
            if len(transitos_grupo) == 1:
                transitos_filtrados.append(transitos_grupo[0])
                continue

            transitos_grupo.sort(key=lambda x: x.jd_exato)

            subclusters = []
            cluster_atual = [transitos_grupo[0]]

            for i in range(1, len(transitos_grupo)):
                if transitos_grupo[i].jd_exato - transitos_grupo[i - 1].jd_exato <= janela_tempo:
                    cluster_atual.append(transitos_grupo[i])
                else:
                    subclusters.append(cluster_atual)
                    cluster_atual = [transitos_grupo[i]]

            if cluster_atual:
                subclusters.append(cluster_atual)

            for cluster in subclusters:
                melhor = min(cluster, key=lambda x: x.orbe)
                transitos_filtrados.append(melhor)

        transitos_filtrados.sort(key=lambda x: x.jd_exato)
        self.transitos = transitos_filtrados

    def calcular_transitos(self, dias_margem: int = 2) -> None:
        """Calcula trânsitos usando metodologia de transito_delph"""
        self.transitos.clear()

        dt_inicio = self.dt_utc - timedelta(days=dias_margem)
        dt_fim = self.dt_utc + timedelta(days=dias_margem)
        jd_inicio = dt_to_jd_utc(dt_inicio)
        jd_fim = dt_to_jd_utc(dt_fim)

        # Buscar aspectos de LONGITUDE
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

        # Buscar PARALELOS E CONTRA-PARALELOS
        for i, p1_nome in enumerate(planetas_list):
            for p2_nome in planetas_list[i + 1:]:
                p1, p2 = PLANETAS[p1_nome], PLANETAS[p2_nome]
                intervalo = determinar_intervalo(p1, p2)
                jd_atual = jd_inicio

                while jd_atual < jd_fim:
                    jd_prox = min(jd_atual + intervalo, jd_fim)

                    dec1 = calcular_declinacao_planeta(jd_atual, p1)
                    dec2 = calcular_declinacao_planeta(jd_atual, p2)

                    gap_par = abs(dec1 - dec2)
                    gap_cpa = abs(dec1 + dec2)

                    if gap_par <= 1.2:
                        jd_exato, orbe_f = buscar_transito_exato(jd_atual, jd_prox, p1, p2, -1.0, 1.2)
                        if jd_exato > 0 and jd_inicio <= jd_exato <= jd_fim:
                            dec1_ex = calcular_declinacao_planeta(jd_exato, p1)
                            dec2_ex = calcular_declinacao_planeta(jd_exato, p2)
                            trans = Transito(jd_exato, p1, p2, -1.0, dec1_ex, dec2_ex, abs(dec1_ex - dec2_ex), 'PAR')
                            self.transitos.append(trans)

                    if gap_cpa <= 1.2:
                        jd_exato, orbe_f = buscar_transito_exato(jd_atual, jd_prox, p1, p2, -2.0, 1.2)
                        if jd_exato > 0 and jd_inicio <= jd_exato <= jd_fim:
                            dec1_ex = calcular_declinacao_planeta(jd_exato, p1)
                            dec2_ex = calcular_declinacao_planeta(jd_exato, p2)
                            trans = Transito(jd_exato, p1, p2, -2.0, dec1_ex, dec2_ex, abs(dec1_ex + dec2_ex), 'CPA')
                            self.transitos.append(trans)

                    jd_atual = jd_prox

        self._deduplicate_transitos(janela_tempo=0.15)

    def calcular_mudancas_signo(self, dias_margem: int = 2) -> None:
        """Calcula entradas de planetas em novos signos"""
        self.mudancas_signo.clear()

        dt_inicio = self.dt_utc - timedelta(days=dias_margem)
        dt_fim = self.dt_utc + timedelta(days=dias_margem)
        jd_inicio = dt_to_jd_utc(dt_inicio)
        jd_fim = dt_to_jd_utc(dt_fim)

        for nome, code in PLANETAS.items():
            intervalo = determinar_intervalo(code, code)
            jd_atual = jd_inicio
            signo_anterior = None

            while jd_atual < jd_fim:
                lon = calcular_posicao_planeta(jd_atual, code)
                signo_atual = int(lon / 30.0) % 12

                if signo_anterior is not None and signo_atual != signo_anterior:
                    # Mudança detectada, refinar
                    jd_mudanca = buscar_mudanca_signo_exata(jd_atual - intervalo, jd_atual, code, signo_anterior)

                    if jd_inicio <= jd_mudanca <= jd_fim:
                        sig_saida = SIGNOS[signo_anterior]
                        sig_entrada = SIGNOS[signo_atual]
                        descricao = f"{nome} entra em {sig_entrada}"

                        evento = EventoAstral(jd_mudanca, 'entrada_signo', descricao)
                        self.mudancas_signo.append(evento)

                signo_anterior = signo_atual
                jd_atual += intervalo

    def calcular_voc_lua(self, dias_margem: int = 2) -> None:
        """Calcula períodos de Lua Vazia (VOC)"""
        self.voc_periodos.clear()

        # Filtrar apenas eventos de entrada de signo da Lua
        mudancas_lua = [e for e in self.mudancas_signo if 'LUA' in e.descricao]

        for mudanca_evento in mudancas_lua:
            jd_mudanca = mudanca_evento.jd_exato

            # Encontrar o último aspecto da Lua antes dessa mudança
            aspectos_lua = [t for t in self.transitos
                            if (t.planeta1 == swe.MOON or t.planeta2 == swe.MOON)
                            and t.jd_exato < jd_mudanca]

            if aspectos_lua:
                ultimo_aspecto = max(aspectos_lua, key=lambda x: x.jd_exato)

                # VOC começa 1 segundo depois do último aspecto
                jd_voc_inicio = ultimo_aspecto.jd_exato + 1 / 86400.0
                jd_voc_fim = jd_mudanca

                duracao_dias = jd_voc_fim - jd_voc_inicio
                duracao_hms = dias_para_hms(duracao_dias)

                # Extrair signo de entrada da descrição
                signo_entrada = mudanca_evento.descricao.split()[-1]

                # Determinar signo de saída
                lon_antes = calcular_posicao_planeta(jd_voc_inicio, swe.MOON)
                signo_saida = SIGNOS[int(lon_antes / 30.0) % 12]

                self.voc_periodos.append({
                    'jd_inicio': jd_voc_inicio,
                    'jd_fim': jd_voc_fim,
                    'signo_saida': signo_saida,
                    'signo_entrada': signo_entrada,
                    'duracao_hms': duracao_hms,
                })

    def compilar_eventos_astral(self) -> None:
        """Compila todos os eventos (trânsitos + mudanças de signo + VOC) em ordem"""
        self.eventos_astral.clear()

        # Adicionar trânsitos
        for trans in self.transitos:
            p1_nome = PLANETA_REV.get(trans.planeta1, f'PL{trans.planeta1}')
            p2_nome = PLANETA_REV.get(trans.planeta2, f'PL{trans.planeta2}')

            if trans.tipo in ['PAR', 'CPA']:
                descricao = f"[{p1_nome} {trans.tipo} {p2_nome}] - DECL [{trans.pos_planeta1:.2f}° / {trans.pos_planeta2:.2f}°] - {trans.orbe:.5f}"
            else:
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

        # Adicionar mudanças de signo
        for evento in self.mudancas_signo:
            self.eventos_astral.append(evento)

        # Adicionar VOC
        for voc in self.voc_periodos:
            descricao = f"LUA Fora de Curso durante {voc['duracao_hms']} até entrar em {voc['signo_entrada']}"
            evento = EventoAstral(voc['jd_inicio'], 'voc', descricao)
            self.eventos_astral.append(evento)

        # Ordenar por tempo
        self.eventos_astral.sort()

    def gerar_relatorio(self, incluir_transitos: bool = True) -> str:
        self.calcular_planetas()
        self.calcular_casas()
        self.calcular_aspectos()

        if incluir_transitos:
            self.calcular_transitos()
            self.calcular_mudancas_signo()
            self.calcular_voc_lua()
            self.compilar_eventos_astral()

        rel: List[str] = []
        rel.append("=" * 100)
        rel.append(self.nome_mapa or "MAPA ASTRAL COMPLETO")
        rel.append("=" * 100)
        rel.append(
            f"Data: {self.dia:02d}/{self.mes:02d}/{self.ano}  Hora: {self.hora:02d}:{self.minuto:02d}:{self.segundo:02d} (UTC {self.timezone_horas:+.2f}h)")
        if any([self.cidade, self.estado, self.pais]):
            rel.append(f"Local: {self.cidade} / {self.estado} / {self.pais}")
        rel.append(f"Latitude: {self.latitude:.6f}°  Longitude: {self.longitude:.6f}°")
        rel.append(f"Sistema de Casas: {self.house_system_label}")
        rel.append("=" * 100)
        rel.append("")

        rel.append("PLANETAS:")
        rel.append("-" * 100)
        for nome in list(PLANETAS.keys()) + ['ASC', 'MC']:
            if nome in self.planetas:
                c = self.planetas[nome]
                mov = c.mov.upper()
                decl_txt = f" - DECL [{c.decl:.2f}°]" if c.decl is not None else ''
                rel.append(f"{nome:3s} [{c.pos_str} {c.signo}] {mov}{decl_txt}")

        rel.append("")
        rel.append("=" * 100)
        rel.append("CASAS ASTROLÓGICAS:")
        rel.append("-" * 100)
        for num in range(1, 13):
            c = self.casas[num]
            rel.append(f"Casa {num:2d}: {c['posicao']} {c['signo']}")

        rel.append("")
        rel.append("=" * 100)
        rel.append(f"ASPECTOS DO MAPA ASTRAL ({len(self.aspectos_natais)}):")
        rel.append("-" * 100)
        for asp in sorted(self.aspectos_natais, key=lambda x: x['orbe']):
            linha = f"{asp['p1']:3s} [{asp['pos1']} {asp['sig1']}] {asp['cod']} {asp['p2']:3s} [{asp['pos2']} {asp['sig2']}] - Orbe: {asp['orbe']:.2f}°"
            rel.append(linha)

        if incluir_transitos and self.eventos_astral:
            rel.append("")
            rel.append("=" * 100)
            rel.append(f"TRÂNSITOS, ENTRADAS E VOC ({len(self.eventos_astral)}):")
            rel.append("-" * 100)

            momento_mapa = self.jd
            rel_mostrou_mapa = False

            for evento in self.eventos_astral:
                # Marcar o momento do mapa
                if not rel_mostrou_mapa and evento.jd_exato >= momento_mapa:
                    dt_mapa = jd_para_datetime(momento_mapa, self.timezone_horas)
                    rel.append(f"{dt_mapa.strftime('%d/%m/%Y %H:%M:%S')} <-------- MOMENTO DO MAPA ASTRAL")
                    rel_mostrou_mapa = True

                dt_evento = jd_para_datetime(evento.jd_exato, self.timezone_horas)
                dt_str = dt_evento.strftime('%d/%m/%Y %H:%M:%S')

                linha = f"{dt_str} - {evento.descricao}"
                rel.append(linha)

            # Se o mapa não foi mostrado ainda
            if not rel_mostrou_mapa:
                dt_mapa = jd_para_datetime(momento_mapa, self.timezone_horas)
                rel.append(f"{dt_mapa.strftime('%d/%m/%Y %H:%M:%S')} <-------- MOMENTO DO MAPA ASTRAL")

        rel.append("")
        rel.append("=" * 100)
        rel.append("Calculado com Swiss Ephemeris")
        rel.append("=" * 100)
        return "\n".join(rel)


# ========== CITY FINDER ==========

class CityFinder(tk.Toplevel):
    def __init__(self, master, cidmundo_path: str, on_pick, start_query: str = ""):
        super().__init__(master)
        self.title('Buscar Cidade (CidMundo.txt)')
        self.geometry('820x400')
        self.on_pick = on_pick
        self.rows: List[CityRow] = []
        self.filtered: List[CityRow] = []
        self.iid_map = {}

        frm = ttk.Frame(self);
        frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        top = ttk.Frame(frm);
        top.pack(fill=tk.X)
        ttk.Label(top, text='Buscar:').pack(side=tk.LEFT)
        self.var_q = tk.StringVar(value=start_query or "")
        ent = ttk.Entry(top, textvariable=self.var_q)
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        ttk.Button(top, text='Filtrar', command=self.apply_filter).pack(side=tk.LEFT)

        cols = ('country', 'state', 'city', 'lat', 'lon', 'tz_id', 'utc')
        self.tree = ttk.Treeview(frm, columns=cols, show='headings')
        for c in cols:
            self.tree.heading(c, text=c.upper());
            self.tree.column(c, anchor=tk.W, width=120)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=6)
        self.tree.bind('<Double-1>', self._on_double)

        bt = ttk.Frame(frm);
        bt.pack(fill=tk.X)
        ttk.Button(bt, text='Selecionar', command=self.pick_selected).pack(side=tk.RIGHT)
        ttk.Button(bt, text='Fechar', command=self.destroy).pack(side=tk.RIGHT, padx=6)

        self.load_file(cidmundo_path)
        if (start_query or "").strip():
            self.apply_filter()
        ent.focus_set()

    # def load_file(self, path: str):
    #     if not os.path.exists(path):
    #         messagebox.showerror('Erro', f"CidMundo.txt não encontrado");
    #         return
    def load_file(self, path: str):
        # Se for caminho relativo, procura o arquivo empacotado
        if not os.path.isabs(path):
               path = get_resource_path(path)

        if not os.path.exists(path):
                messagebox.showerror('Erro', f"CidMundo.txt não encontrado em {path}")
                return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = f.read()
        except:
            try:
                with open(path, 'r', encoding='latin-1') as f:
                    data = f.read()
            except:
                return

        for line in data.splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            parts = line.split('|')
            try:
                cc, country, state, city, lat, lon, tzcode, tzid, utc = parts[:9]
                self.rows.append(CityRow(cc, country, state, city, float(lat), float(lon), tzcode, tzid, float(utc)))
            except:
                continue
        self.filtered = list(self.rows);
        self.refresh()

    def apply_filter(self):
        q = strip_accents(self.var_q.get().strip().lower())
        if not q:
            self.filtered = self.rows
        else:
            self.filtered = [r for r in self.rows if (
                    q in strip_accents(r.country.lower()) or q in strip_accents(r.state.lower()) or q in strip_accents(
                r.city.lower())
            )]
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.iid_map.clear()
        for i, r in enumerate(self.filtered[:5000]):
            iid = self.tree.insert('', tk.END,
                                   values=(r.country, r.state, r.city, f"{r.lat:.5f}", f"{r.lon:.5f}", r.tz_id,
                                           r.utc_offset))
            self.iid_map[iid] = i

    def pick_selected(self):
        sel = self.tree.selection()
        if not sel: return
        iid = sel[0]
        if iid not in self.iid_map: return
        idx = self.iid_map[iid]
        row = self.filtered[idx]
        self.on_pick(row);
        self.destroy()

    def _on_double(self, _):
        self.pick_selected()


# ========== UI PRINCIPAL ==========

class JanelaEntrada:
    def __init__(self, root):
        self.root = root
        self.root.title('Mapa Astral com Trânsitos (mapa_ah)')
        self.root.geometry('350x320')
        self.root.resizable(False, False)

        now = datetime.now()
        self.nome_mapa = tk.StringVar(value='Mapa do Momento')
        self.dia = tk.StringVar(value=str(now.day))
        self.mes = tk.StringVar(value=str(now.month))
        self.ano = tk.StringVar(value=str(now.year))
        self.hora = tk.StringVar(value=str(now.hour))
        self.minuto = tk.StringVar(value=f"{now.minute}")
        self.segundo = tk.StringVar(value=f"{now.second}")

        self.cidade = tk.StringVar(value='Brasília')
        self.estado = tk.StringVar(value='DF')
        self.pais = tk.StringVar(value='Brazil')

        self.lat_deg = tk.StringVar(value='15')
        self.lat_min = tk.StringVar(value='46')
        self.lat_sec = tk.StringVar(value='12')
        self.lat_hemi = tk.StringVar(value='S')
        self.lon_deg = tk.StringVar(value='47')
        self.lon_min = tk.StringVar(value='55')
        self.lon_sec = tk.StringVar(value='12')
        self.lon_hemi = tk.StringVar(value='W')
        self.timezone = tk.StringVar(value='-3')

        self.house_system_label = tk.StringVar(value='Regiomontanus')
        self.dias_margem = tk.StringVar(value='2')

        self._build()

    def _build(self):
        main = ttk.Frame(self.root, padding=6)
        main.grid(row=0, column=0, sticky='nsew')
        main.grid_columnconfigure(0, weight=1)

        r = 0
        ttk.Label(main, text='MAPA ASTRAL + TRÂNSITOS', font=('Helvetica', 14, 'bold')).grid(
            row=r, column=0, columnspan=6, pady=(0, 6), sticky='w')

        r += 1
        frm_nome = ttk.LabelFrame(main, text='Identificação')
        frm_nome.grid(row=r, column=0, columnspan=6, sticky='ew', pady=(2, 2))
        frm_nome.grid_columnconfigure(1, weight=1)
        ttk.Label(frm_nome, text='Nome:').grid(row=0, column=0, sticky='e', padx=(4, 6))
        ttk.Entry(frm_nome, textvariable=self.nome_mapa, width=28).grid(row=0, column=1, sticky='w')

        r += 1
        frm_dt = ttk.LabelFrame(main, text='Data e Hora (Local)')
        frm_dt.grid(row=r, column=0, columnspan=6, sticky='ew', pady=(2, 2))
        for c in range(12): frm_dt.grid_columnconfigure(c, weight=0)
        frm_dt.grid_columnconfigure(11, weight=1)

        ttk.Label(frm_dt, text='Data:').grid(row=0, column=0, sticky='e', padx=(2, 2))
        ttk.Entry(frm_dt, textvariable=self.dia, width=3, justify='center').grid(row=0, column=1)
        ttk.Label(frm_dt, text='/').grid(row=0, column=2)
        ttk.Entry(frm_dt, textvariable=self.mes, width=3, justify='center').grid(row=0, column=3)
        ttk.Label(frm_dt, text='/').grid(row=0, column=4)
        ttk.Entry(frm_dt, textvariable=self.ano, width=4, justify='center').grid(row=0, column=5)

        ttk.Label(frm_dt, text='Hora:').grid(row=0, column=6, sticky='e', padx=(6, 2))
        ttk.Entry(frm_dt, textvariable=self.hora, width=3, justify='center').grid(row=0, column=7)
        ttk.Label(frm_dt, text=':').grid(row=0, column=8)
        ttk.Entry(frm_dt, textvariable=self.minuto, width=3, justify='center').grid(row=0, column=9)
        ttk.Label(frm_dt, text=':').grid(row=0, column=10)
        ttk.Entry(frm_dt, textvariable=self.segundo, width=3, justify='center').grid(row=0, column=11)

        r += 1
        frm_loc = ttk.LabelFrame(main, text='Localização')
        frm_loc.grid(row=r, column=0, columnspan=6, sticky='ew', pady=(2, 2))
        ttk.Label(frm_loc, text='Cidade:').grid(row=0, column=0, sticky='e', padx=(2, 2))
        ttk.Entry(frm_loc, textvariable=self.cidade, width=14).grid(row=0, column=1)
        ttk.Label(frm_loc, text='Estado:').grid(row=0, column=2, sticky='e', padx=(2, 2))
        ttk.Entry(frm_loc, textvariable=self.estado, width=4).grid(row=0, column=3)
        ttk.Button(frm_loc, text='Buscar', command=self.buscar_cidade).grid(row=1, column=1, sticky='w')

        r += 1
        frm_geo = ttk.LabelFrame(main, text='Coordenadas (DMS)')
        frm_geo.grid(row=r, column=0, columnspan=6, sticky='ew', pady=(2, 2))
        for c in range(12): frm_geo.grid_columnconfigure(c, weight=0)

        ttk.Label(frm_geo, text='Lat:').grid(row=0, column=0, sticky='e', padx=(2, 2))
        ttk.Entry(frm_geo, textvariable=self.lat_deg, width=3, justify='center').grid(row=0, column=1)
        ttk.Entry(frm_geo, textvariable=self.lat_min, width=3, justify='center').grid(row=0, column=2)
        ttk.Entry(frm_geo, textvariable=self.lat_sec, width=3, justify='center').grid(row=0, column=3)
        ttk.Combobox(frm_geo, textvariable=self.lat_hemi, values=('N', 'S'), width=2, state='readonly').grid(row=0,
                                                                                                             column=4,
                                                                                                             padx=2)

        ttk.Label(frm_geo, text='Lon:').grid(row=0, column=5, sticky='e', padx=(2, 2))
        ttk.Entry(frm_geo, textvariable=self.lon_deg, width=3, justify='center').grid(row=0, column=6)
        ttk.Entry(frm_geo, textvariable=self.lon_min, width=3, justify='center').grid(row=0, column=7)
        ttk.Entry(frm_geo, textvariable=self.lon_sec, width=3, justify='center').grid(row=0, column=8)
        ttk.Combobox(frm_geo, textvariable=self.lon_hemi, values=('E', 'W'), width=2, state='readonly').grid(row=0,
                                                                                                             column=9,
                                                                                                             padx=2)

        ttk.Label(frm_geo, text='UTC:').grid(row=1, column=0, sticky='e', padx=(2, 2))
        ttk.Entry(frm_geo, textvariable=self.timezone, width=4, justify='center').grid(row=1, column=1)

        ttk.Label(frm_geo, text='Margem:').grid(row=1, column=5, sticky='e', padx=(2, 2))
        ttk.Entry(frm_geo, textvariable=self.dias_margem, width=3, justify='center').grid(row=1, column=6)
        ttk.Label(frm_geo, text='dias').grid(row=1, column=7, sticky='w')

        r += 1
        bottom = ttk.Frame(main)
        bottom.grid(row=r, column=0, columnspan=6, sticky='ew', pady=(6, 2))
        bottom.grid_columnconfigure(0, weight=1)

        ttk.Label(bottom, text='Sistema:').pack(side='left', padx=(0, 6))
        ttk.Combobox(bottom, textvariable=self.house_system_label,
                     values=list(HOUSE_SYSTEMS.keys()), width=16, state='readonly').pack(side='left')

        ttk.Button(bottom, text='CALCULAR', command=self.calcular_mapa).pack(side='right', padx=6)

    def buscar_cidade(self):
        def on_pick(row: CityRow):
            self.cidade.set(row.city);
            self.estado.set(row.state)
            latd, latm, lats, latH = dec_to_dms_components(row.lat, True)
            lond, lonm, lons, lonH = dec_to_dms_components(row.lon, False)
            self.lat_deg.set(str(latd));
            self.lat_min.set(str(latm));
            self.lat_sec.set(str(lats));
            self.lat_hemi.set(latH)
            self.lon_deg.set(str(lond));
            self.lon_min.set(str(lonm));
            self.lon_sec.set(str(lons));
            self.lon_hemi.set(lonH)
            self.timezone.set(str(row.utc_offset))

        # CityFinder(self.root, 'CidMundo.txt', on_pick, start_query=self.cidade.get())

        cidmundo_path = get_resource_path('CidMundo.txt')
        CityFinder(self.root, cidmundo_path, on_pick, start_query=self.cidade.get())

    def validar(self):
        try:
            nome = self.nome_mapa.get().strip()
            d = int(self.dia.get());
            m = int(self.mes.get());
            a = int(self.ano.get())
            h = int(self.hora.get());
            mi = int(self.minuto.get());
            s = int(self.segundo.get())
            latdeg = int(self.lat_deg.get());
            latmin = int(self.lat_min.get());
            latsec = int(self.lat_sec.get());
            latH = self.lat_hemi.get()
            londeg = int(self.lon_deg.get());
            lonmin = int(self.lon_min.get());
            lonsec = int(self.lon_sec.get());
            lonH = self.lon_hemi.get()
            tz = float(self.timezone.get())
            dias = int(self.dias_margem.get())

            lat_dec = dms_to_decimal(latdeg, latmin, latsec, latH, True)
            lon_dec = dms_to_decimal(londeg, lonmin, lonsec, lonH, False)

            if not (1 <= d <= 31): raise ValueError('Dia 1-31')
            if not (1 <= m <= 12): raise ValueError('Mês 1-12')
            if not (1900 <= a <= 2100): raise ValueError('Ano 1900-2100')
            if not (0 <= h <= 23): raise ValueError('Hora 0-23')
            if not (0 <= mi <= 59): raise ValueError('Minuto 0-59')
            if not (0 <= s <= 59): raise ValueError('Segundo 0-59')
            if not (-90.0 <= lat_dec <= 90.0): raise ValueError('Latitude inválida')
            if not (-180.0 <= lon_dec <= 180.0): raise ValueError('Longitude inválida')
            if not (-12 <= tz <= 14): raise ValueError('UTC -12 a 14')

            return (nome, d, m, a, h, mi, s, lat_dec, lon_dec, tz, self.cidade.get().strip(),
                    self.estado.get().strip(), self.pais.get().strip(), self.house_system_label.get(), dias)
        except ValueError as e:
            messagebox.showerror('Erro', str(e));
            return None

    def calcular_mapa(self):
        vals = self.validar()
        if not vals: return

        (nome, d, m, a, h, mi, s, lat_dec, lon_dec, tz, cidade, estado, pais, house_label, dias) = vals

        try:
            mapa = MapaAstral(nome, d, m, a, h, mi, s, lat_dec, lon_dec, tz, cidade, estado, pais,
                              house_system_label=house_label)
            rel = mapa.gerar_relatorio(incluir_transitos=True)
            JanelaResultado(self.root, rel)
        except Exception as e:
            messagebox.showerror('Erro', f'Ocorreu um erro: {e!r}')


class JanelaResultado:
    def __init__(self, parent, relatorio: str):
        self.win = tk.Toplevel(parent)
        self.win.title('Resultado - Mapa Astral + Trânsitos')
        self.win.geometry('750x700')

        frm = ttk.Frame(self.win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        self.texto = scrolledtext.ScrolledText(frm, wrap=tk.NONE, font=('Courier New', 9), bg='#f5f5f5', height=26)
        self.texto.pack(fill=tk.BOTH, expand=True)
        self.texto.insert('1.0', relatorio)

        btnbar = ttk.Frame(frm)
        btnbar.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btnbar, text='Copiar', command=self.copy_report).pack(side=tk.LEFT)
        ttk.Button(btnbar, text='Fechar', command=self.win.destroy).pack(side=tk.RIGHT)

    def copy_report(self):
        txt = self.texto.get('1.0', tk.END)
        self.win.clipboard_clear()
        self.win.clipboard_append(txt)
        messagebox.showinfo('Copiado', 'Relatório copiado para a área de transferência.')


def main():
    root = tk.Tk()
    app = JanelaEntrada(root)
    root.mainloop()


if __name__ == '__main__':
    main()