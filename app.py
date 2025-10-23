# -*- coding: utf-8 -*-
import os
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Optional
from dataclasses import dataclass
from flask import Flask, request, jsonify

try:
    import swisseph as swe
except Exception as e:
    raise RuntimeError("Swiss Ephemeris (swisseph) é obrigatório para esta aplicação.")

app = Flask(__name__)

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
PLANETAS_MOVEIS = [swe.MOON, swe.MERCURY, swe.VENUS, swe.MARS]

# --------------------------- Utilitários básicos --------------------------- #

def normalize_angle(x: float) -> float:
    x = x % 360.0
    return x if x >= 0 else x + 360.0


def angular_difference(a: float, b: float) -> float:
    """Diferença angular mínima em graus (0..180)."""
    d = abs((a % 360.0) - (b % 360.0))
    return d if d <= 180.0 else 360.0 - d


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


def dt_to_jd_utc(dt_utc):
    frac = (dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0)
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, frac, 1)


def jd_para_datetime(jd, tz_offset=0.0):
    year, month, day, hour = swe.revjul(jd + tz_offset / 24.0)
    hour_int = int(hour)
    minute = int((hour - hour_int) * 60)
    second = int(((hour - hour_int) * 60 - minute) * 60)
    return datetime(year, month, day, hour_int, minute, second)


def dias_para_hms(dias: float) -> str:
    dias = abs(dias)
    horas = dias * 24
    h = int(horas)
    minutos = (horas - h) * 60
    m = int(minutos)
    segundos = int((minutos - m) * 60)
    return f"{h:02d}:{m:02d}:{segundos:02d}"


def calcular_posicao_planeta(jd, planeta):
    pos, _ = swe.calc_ut(jd, planeta)
    return float(pos[0]) % 360.0


def calcular_declinacao_planeta(jd: float, planeta: int) -> float:
    eq, _ = swe.calc_ut(jd, planeta, swe.FLG_SWIEPH | swe.FLG_EQUATORIAL)
    return float(eq[1])


def determinar_intervalo(planeta1: int, planeta2: int) -> float:
    planeta_lento = max(planeta1, planeta2)
    intervalos = {
        swe.MOON: 0.005,
        swe.MERCURY: 0.02,
        swe.VENUS: 0.02,
        swe.SUN: 0.05,
        swe.MARS: 0.05,
        swe.JUPITER: 0.1,
        swe.SATURN: 0.2,
        swe.URANUS: 0.5,
        swe.NEPTUNE: 0.5,
        swe.PLUTO: 0.5,
        swe.TRUE_NODE: 0.2,
    }
    return intervalos.get(planeta_lento, 0.5)

# --------------------------- Dataclasses --------------------------- #

@dataclass
class Corpo:
    nome: str
    lon: float
    lat: float
    vel: float
    mov: str
    signo: str
    pos_str: str
    tipo: str = 'planeta'


@dataclass
class PontoFixo:
    nome: str
    lon: float
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
    planeta2_nome: str = ''


@dataclass
class EventoAstral:
    jd_exato: float
    tipo: str
    descricao: str

    def __lt__(self, other):
        return self.jd_exato < other.jd_exato


# --------------------------- Núcleo de busca de trânsitos --------------------------- #

def buscar_transito_exato(jd_inicio: float, jd_fim: float, planeta1: int, planeta2: int,
                          angulo_aspecto: float, orbe: float, eh_ponto_fixo: bool = False) -> Tuple[float, float]:
    NUM_SAMPLES = 24
    BISSECCOES_MAX = 10
    ORBE_LIMITE = orbe * 1.5

    def calcular_orbe_atual(jd: float) -> float:
        p1 = calcular_posicao_planeta(jd, planeta1)
        p2 = planeta2 if eh_ponto_fixo else calcular_posicao_planeta(jd, planeta2)
        diff = angular_difference(p1, p2)
        return diff - angulo_aspecto

    delta_tempo = (jd_fim - jd_inicio) / (NUM_SAMPLES - 1)
    amostras = []
    melhor_orbe = 999.0
    melhor_jd = 0.0

    for i in range(NUM_SAMPLES):
        jd_sample = jd_inicio + i * delta_tempo
        orbe_val = abs(calcular_orbe_atual(jd_sample))
        amostras.append((jd_sample, orbe_val))
        if orbe_val < melhor_orbe:
            melhor_orbe = orbe_val
            melhor_jd = jd_sample

    if melhor_orbe > ORBE_LIMITE:
        return 0.0, 999.0

    # Estreita ao redor do mínimo local
    jd1, jd2 = 0.0, 0.0
    for i in range(1, NUM_SAMPLES - 1):
        if amostras[i - 1][1] > amostras[i][1] < amostras[i + 1][1]:
            jd1, jd2 = amostras[i - 1][0], amostras[i + 1][0]
            break

    if jd1 == 0.0:
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

    return (melhor_jd, melhor_orbe) if melhor_orbe <= orbe else (0.0, 999.0)


def buscar_mudanca_signo_exata(jd1: float, jd2: float, planeta: int, signo_saida: int) -> float:
    BISSECCOES_MAX = 20

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
        if abs(jd2 - jd1) < 1.0e-12:
            return jd_meio
    return (jd1 + jd2) / 2

# --------------------------- Estrelas Fixas --------------------------- #

@dataclass
class EstrelaFixa:
    nome: str
    constelacao: str
    lon: Optional[float]  # pode vir do arquivo; se None, usa Swiss Ephemeris pelo nome


def ler_estrelas_arquivo(caminho: str) -> List[EstrelaFixa]:
    """Lê arquivo TAB. Aceita 2 formatos:
    1) Nome	Constelação	... (sem longitude) -> lon=None e será resolvida via swe.fixstar2
    2) Nome	Constelação	Longitude (graus decimais) -> usa valor
    Demais colunas são ignoradas.
    """
    estrelas: List[EstrelaFixa] = []
    if not os.path.exists(caminho):
        return estrelas
    with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('	')
            if len(parts) < 2:
                continue
            nome = parts[0].strip()
            const = parts[1].strip()
            lon: Optional[float] = None
            # tenta 3ª coluna como longitude (opcional)
            if len(parts) >= 3:
                try:
                    test = parts[2].replace(',', '.')
                    lon_val = float(test)
                    lon = normalize_angle(lon_val)
                except Exception:
                    lon = None
            estrelas.append(EstrelaFixa(nome=nome, constelacao=const, lon=lon))
    return estrelas


def longitude_estrela_por_nome(jd_ut: float, nome: str) -> Optional[float]:
    """Tenta obter a longitude eclíptica (equinócio da data) via Swiss Ephemeris pelo nome da estrela."""
    try:
        # swe.fixstar2 retorna [lon, lat, dist, ra, dec, ...] em eclíptica/equinócio da data por padrão
        # Documentação: longitude eclíptica aparente (true) – ideal para conjunções e oposições por longitude
        pos, _ = swe.fixstar2(nome)
        lon = float(pos[0]) % 360.0
        return lon
    except Exception:
        return None


# --------------------------- Classe principal --------------------------- #

class MapaAstral:
    def __init__(self, nome_mapa, dia, mes, ano, hora, minuto, segundo,
                 latitude_dec, longitude_dec, timezone_horas, cidade='', estado='', pais='',
                 house_system_label='Regiomontanus', estrelas_orbe_graus: float = 0.10):
        self.nome_mapa = nome_mapa.strip()
        self.dia, self.mes, self.ano = dia, mes, ano
        self.hora, self.minuto, self.segundo = hora, minuto, segundo
        self.latitude, self.longitude = latitude_dec, longitude_dec
        self.timezone_horas = timezone_horas
        self.cidade, self.estado, self.pais = cidade, estado, pais
        self.house_system_label = house_system_label
        self.estrelas_orbe_graus = float(estrelas_orbe_graus)

        self.dt_local = datetime(ano, mes, dia, hora, minuto, segundo)
        self.dt_utc = self.dt_local - timedelta(hours=timezone_horas)
        self.jd = dt_to_jd_utc(self.dt_utc)

        self.planetas: Dict[str, Corpo] = {}
        self.pontos_fixos: Dict[str, PontoFixo] = {}
        self.casas = {}
        self.aspectos_natais = []
        self.transitos: List[Transito] = []
        self.mudancas_signo: List[EventoAstral] = []
        self.voc_periodos: List[Dict] = []
        self.eventos_astral: List[EventoAstral] = []
        self.estrelas_lista: List[EstrelaFixa] = []
        self.estrelas_hits: List[Dict] = []

        swe.set_ephe_path(None)

    # --------- cálculos básicos do mapa --------- #
    def calcular_pontos_fixos(self):
        self.pontos_fixos.clear()
        casas, _ = swe.houses(self.jd, self.latitude, self.longitude, b'R')
        asc_lon = float(casas[0])
        mc_lon = float(casas[9])
        sol_lon = calcular_posicao_planeta(self.jd, swe.SUN)
        lua_lon = calcular_posicao_planeta(self.jd, swe.MOON)
        fortuna_lon = (asc_lon + lua_lon - sol_lon) % 360.0
        asc_sig, asc_pos = graus_para_signo_posicao(asc_lon)
        mc_sig, mc_pos = graus_para_signo_posicao(mc_lon)
        for_sig, for_pos = graus_para_signo_posicao(fortuna_lon)
        self.pontos_fixos['ASC'] = PontoFixo('ASC', asc_lon, asc_sig, asc_pos)
        self.pontos_fixos['MC'] = PontoFixo('MC', mc_lon, mc_sig, mc_pos)
        self.pontos_fixos['FOR'] = PontoFixo('FOR', fortuna_lon, for_sig, for_pos)

    def calcular_planetas(self):
        self.planetas.clear()
        for nome, code in PLANETAS.items():
            pos, _ = swe.calc_ut(self.jd, code)
            lon, lat, lon_speed = float(pos[0]), float(pos[1]), float(pos[3])
            mov = 'dir' if lon_speed >= 0 else 'ret'
            signo, pos_str = graus_para_signo_posicao(lon)
            self.planetas[nome] = Corpo(nome, lon % 360.0, lat, lon_speed, mov, signo, pos_str, 'planeta')

    def calcular_casas(self):
        self.casas.clear()
        casas, _ = swe.houses(self.jd, self.latitude, self.longitude, b'R')
        for i in range(12):
            lon = float(casas[i])
            s, p = graus_para_signo_posicao(lon)
            self.casas[i + 1] = {'longitude': lon, 'signo': s, 'posicao': p}

    # --------- aspectos natais (entre corpos/pontos) --------- #
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
                            'tipo': 'planeta-planeta',
                        })
        # Planeta x pontos
        for p1_nome in PLANETAS.keys():
            p1 = self.planetas[p1_nome]
            for pf_nome in ['ASC', 'MC', 'FOR']:
                if pf_nome in self.pontos_fixos:
                    pf = self.pontos_fixos[pf_nome]
                    dif = angular_difference(p1.lon, pf.lon)
                    for cod, (alvo, orbe) in ASPECTOS.items():
                        gap = abs(dif - alvo)
                        if gap <= orbe:
                            sig1, pos1 = graus_para_signo_posicao(p1.lon)
                            self.aspectos_natais.append({
                                'p1': p1_nome, 'p2': pf_nome, 'cod': cod, 'orbe': gap,
                                'pos1': pos1, 'sig1': sig1, 'pos2': pf.pos_str, 'sig2': pf.signo,
                                'tipo': 'planeta-ponto',
                            })
        # Ponto x Ponto
        pontos_nomes = ['ASC', 'MC', 'FOR']
        for i, pf1_nome in enumerate(pontos_nomes):
            if pf1_nome not in self.pontos_fixos:
                continue
            pf1 = self.pontos_fixos[pf1_nome]
            for pf2_nome in pontos_nomes[i + 1:]:
                if pf2_nome not in self.pontos_fixos:
                    continue
                pf2 = self.pontos_fixos[pf2_nome]
                dif = angular_difference(pf1.lon, pf2.lon)
                for cod, (alvo, orbe) in ASPECTOS.items():
                    gap = abs(dif - alvo)
                    if gap <= orbe:
                        self.aspectos_natais.append({
                            'p1': pf1_nome, 'p2': pf2_nome, 'cod': cod, 'orbe': gap,
                            'pos1': pf1.pos_str, 'sig1': pf1.signo, 'pos2': pf2.pos_str, 'sig2': pf2.signo,
                            'tipo': 'ponto-ponto',
                        })

    # --------- trânsitos (como no seu código) --------- #
    def _deduplicate_transitos(self, janela_tempo: float = 0.15) -> None:
        if not self.transitos:
            return
        grupos = {}
        for trans in self.transitos:
            asp_key = trans.tipo if trans.tipo in ['PAR', 'CPA'] else round(trans.aspecto, 1)
            chave = (trans.planeta1, trans.planeta2, asp_key)
            grupos.setdefault(chave, []).append(trans)
        transitos_filtrados = []
        for _, transitos_grupo in grupos.items():
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

    def calcular_transitos(self, dias_margem: int = 2):
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
                            jd_exato, orbe_final = buscar_transito_exato(
                                jd_atual, jd_prox, p1, p2, aspecto_deg, orbe, False
                            )
                            if jd_exato > 0 and jd_inicio <= jd_exato <= jd_fim and orbe_final < 0.005:
                                pos1_ex = calcular_posicao_planeta(jd_exato, p1)
                                pos2_ex = calcular_posicao_planeta(jd_exato, p2)
                                trans = Transito(jd_exato, p1, p2, aspecto_deg, pos1_ex, pos2_ex, orbe_final, 'aspecto', p2_nome)
                                self.transitos.append(trans)
                        jd_atual = jd_prox
        # Planetas móveis x pontos fixos
        for ponto_nome, ponto_obj in self.pontos_fixos.items():
            for planeta_nome in [nome for nome, code in PLANETAS.items() if code in PLANETAS_MOVEIS]:
                planeta_code = PLANETAS[planeta_nome]
                for aspecto_deg, orbe in ORBES_PADRAO.items():
                    intervalo = determinar_intervalo(planeta_code, planeta_code)
                    jd_atual = jd_inicio
                    while jd_atual < jd_fim:
                        jd_prox = min(jd_atual + intervalo, jd_fim)
                        pos1 = calcular_posicao_planeta(jd_atual, planeta_code)
                        diff_atual = angular_difference(pos1, ponto_obj.lon)
                        pos1_prox = calcular_posicao_planeta(jd_prox, planeta_code)
                        diff_prox = angular_difference(pos1_prox, ponto_obj.lon)
                        gap_atual = abs(diff_atual - aspecto_deg)
                        gap_prox = abs(diff_prox - aspecto_deg)
                        if min(gap_atual, gap_prox) <= orbe:
                            jd_exato, orbe_final = buscar_transito_exato(
                                jd_atual, jd_prox, planeta_code, ponto_obj.lon, aspecto_deg, orbe, True
                            )
                            if jd_exato > 0 and jd_inicio <= jd_exato <= jd_fim and orbe_final < 0.005:
                                pos1_ex = calcular_posicao_planeta(jd_exato, planeta_code)
                                trans = Transito(jd_exato, planeta_code, -1, aspecto_deg, pos1_ex, ponto_obj.lon, orbe_final, 'aspecto', ponto_nome)
                                self.transitos.append(trans)
                        jd_atual = jd_prox
        self._deduplicate_transitos(janela_tempo=0.15)

    # --------- mudanças de signo e Lua VOC --------- #
    def calcular_mudancas_signo(self, dias_margem: int = 2):
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
                    jd_mudanca = buscar_mudanca_signo_exata(jd_atual - intervalo, jd_atual, code, signo_anterior)
                    if jd_inicio <= jd_mudanca <= jd_fim:
                        sig_entrada = SIGNOS[signo_atual]
                        descricao = f"{nome} entra em {sig_entrada}"
                        evento = EventoAstral(jd_mudanca, 'entrada_signo', descricao)
                        self.mudancas_signo.append(evento)
                signo_anterior = signo_atual
                jd_atual += intervalo

    def calcular_voc_lua(self):
        self.voc_periodos.clear()
        mudancas_lua = [e for e in self.mudancas_signo if 'LUA' in e.descricao]
        for mudanca_evento in mudancas_lua:
            jd_mudanca = mudanca_evento.jd_exato
            aspectos_lua = [t for t in self.transitos
                            if (t.planeta1 == swe.MOON or t.planeta2 == swe.MOON)
                            and t.jd_exato < jd_mudanca]
            if aspectos_lua:
                ultimo_aspecto = max(aspectos_lua, key=lambda x: x.jd_exato)
                jd_voc_inicio = ultimo_aspecto.jd_exato + 1 / 86400.0
                jd_voc_fim = jd_mudanca
                duracao_dias = jd_voc_fim - jd_voc_inicio
                duracao_hms = dias_para_hms(duracao_dias)
                signo_entrada = mudanca_evento.descricao.split()[-1]
                lon_antes = calcular_posicao_planeta(jd_voc_inicio, swe.MOON)
                signo_saida = SIGNOS[int(lon_antes / 30.0) % 12]
                self.voc_periodos.append({
                    'jd_inicio': jd_voc_inicio,
                    'jd_fim': jd_voc_fim,
                    'signo_saida': signo_saida,
                    'signo_entrada': signo_entrada,
                    'duracao_hms': duracao_hms,
                })

    # --------- Estrelas Fixas: CJN/OPO com planetas e pontos fixos --------- #
    def carregar_estrelas(self):
        base_dir = os.path.dirname(__file__)
        caminho = os.path.join(base_dir, 'Estrelas_Fixas.txt')
        self.estrelas_lista = ler_estrelas_arquivo(caminho)

    def calcular_estrelas_aspectos(self):
        self.estrelas_hits.clear()
        if not self.estrelas_lista:
            self.carregar_estrelas()
        if not self.estrelas_lista:
            return
        # Alvos: todos os planetas + pontos fixos principais
        alvos: List[Tuple[str, float, str]] = []  # (nome, lon, tipo: 'P'|'PT')
        for nome, corpo in self.planetas.items():
            alvos.append((nome, corpo.lon, 'P'))
        for pf in ['ASC', 'MC', 'FOR']:
            if pf in self.pontos_fixos:
                alvos.append((pf, self.pontos_fixos[pf].lon, 'PT'))
        orbe = abs(float(self.estrelas_orbe_graus))
        jd = self.jd
        for est in self.estrelas_lista:
            # Resolve longitude da estrela
            if est.lon is not None:
                lon_estrela = est.lon
            else:
                lon_estrela = longitude_estrela_por_nome(jd, est.nome)
            if lon_estrela is None:
                continue  # não foi possível resolver a estrela
            for alvo_nome, alvo_lon, alvo_tipo in alvos:
                dif = angular_difference(lon_estrela, alvo_lon)
                # verifica conjunção (0) ou oposição (180) com orbe
                orbe_cjn = abs(dif - 0.0)
                orbe_opo = abs(dif - 180.0)
                if orbe_cjn <= orbe:
                    asp = 'CJN'
                    orbe_final = orbe_cjn
                elif orbe_opo <= orbe:
                    asp = 'OPO'
                    orbe_final = orbe_opo
                else:
                    continue
                sigE, posE = graus_para_signo_posicao(lon_estrela)
                sigA, posA = graus_para_signo_posicao(alvo_lon)
                self.estrelas_hits.append({
                    'nome': est.nome,
                    'const': est.constelacao,
                    'lonE': lon_estrela,
                    'sigE': sigE,
                    'posE': posE,
                    'alvo': alvo_nome,
                    'alvo_tipo': alvo_tipo,
                    'lonA': alvo_lon,
                    'sigA': sigA,
                    'posA': posA,
                    'asp': asp,
                    'orbe': orbe_final,
                })
        # Ordena por orbe menor
        self.estrelas_hits.sort(key=lambda x: x['orbe'])

    # --------- compila e relatório --------- #
    def compilar_eventos_astral(self):
        self.eventos_astral.clear()
        for trans in self.transitos:
            p1_nome = PLANETA_REV.get(trans.planeta1, f'PL{trans.planeta1}')
            p2_nome = trans.planeta2_nome if trans.planeta2_nome else PLANETA_REV.get(trans.planeta2, f'PL{trans.planeta2}')
            sig1, pos1 = graus_para_signo_posicao(trans.pos_planeta1)
            sig2, pos2 = graus_para_signo_posicao(trans.pos_planeta2)
            asp_cod = None
            for cod, (alvo, _) in ASPECTOS.items():
                if abs(trans.aspecto - alvo) < 0.1:
                    asp_cod = cod
                    break
            asp_cod = asp_cod or '???'
            descricao = f"[{'P-PT' if trans.planeta2 == -1 else 'P-P'}] [{p1_nome} {asp_cod} {p2_nome}] - {pos1} {sig1} / {pos2} {sig2} - {trans.orbe:.5f}"
            evento = EventoAstral(trans.jd_exato, 'aspecto', descricao)
            self.eventos_astral.append(evento)
        for evento in self.mudancas_signo:
            self.eventos_astral.append(evento)
        for voc in self.voc_periodos:
            descricao = f"LUA Fora de Curso durante {voc['duracao_hms']} ate entrar em {voc['signo_entrada']}"
            evento = EventoAstral(voc['jd_inicio'], 'voc', descricao)
            self.eventos_astral.append(evento)
        self.eventos_astral.sort()

    def gerar_relatorio(self):
        self.calcular_pontos_fixos()
        self.calcular_planetas()
        self.calcular_casas()
        self.calcular_aspectos()
        self.calcular_transitos()
        self.calcular_mudancas_signo()
        self.calcular_voc_lua()
        # Estrelas
        self.carregar_estrelas()
        self.calcular_estrelas_aspectos()
        self.compilar_eventos_astral()

        rel = []
        rel.append("=" * 100)
        rel.append(self.nome_mapa or "MAPA ASTRAL COMPLETO")
        rel.append("=" * 100)
        rel.append(
            f"Data: {self.dia:02d}/{self.mes:02d}/{self.ano}  Hora: {self.hora:02d}:{self.minuto:02d}:{self.segundo:02d} (UTC {self.timezone_horas:+.1f}h)")
        if self.cidade or self.estado or self.pais:
            rel.append(f"Local: {self.cidade} / {self.estado} / {self.pais}")
        rel.append(f"Lat: {self.latitude:.6f}  Lon: {self.longitude:.6f}")
        rel.append("=" * 100)
        rel.append("")

        rel.append("PLANETAS:")
        rel.append("-" * 100)
        for nome in PLANETAS.keys():
            if nome in self.planetas:
                c = self.planetas[nome]
                mov = c.mov.upper()
                rel.append(f"{nome:3s} [{c.pos_str} {c.signo}] {mov}")

        rel.append("")
        rel.append("PONTOS FIXOS:")
        rel.append("-" * 100)
        for nome in ['ASC', 'MC', 'FOR']:
            if nome in self.pontos_fixos:
                p = self.pontos_fixos[nome]
                rel.append(f"{nome:3s} [{p.pos_str} {p.signo}]")

        rel.append("")
        rel.append(f"CASAS TERRESTRES por {self.house_system_label}")
        rel.append("-" * 100)
        for num in range(1, 13):
            c = self.casas[num]
            rel.append(f"Casa {num:2d}: {c['posicao']} {c['signo']}")

        rel.append("")
        rel.append(f"ASPECTOS ({len(self.aspectos_natais)}):")
        rel.append("-" * 100)
        for asp in sorted(self.aspectos_natais, key=lambda x: x['orbe']):
            tipo = asp.get('tipo', '').replace('planeta-', 'P-').replace('ponto-', 'PT-')
            linha = f"{asp['p1']:3s} [{asp['pos1']} {asp['sig1']}] {asp['cod']} {asp['p2']:3s} [{asp['pos2']} {asp['sig2']}] - Orbe: {asp['orbe']:.2f} [{tipo}]"
            rel.append(linha)

        rel.append("")
        rel.append("=" * 100)
        rel.append(f"TRANSITOS, ENTRADAS E VOC ({len(self.eventos_astral)}):")
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

        # ----- Secção Estrelas Fixas ----- #
        rel.append("")
        rel.append("=" * 100)
        rel.append(f"ESTRELAS FIXAS — CJN/OPO (±{self.estrelas_orbe_graus:.2f}°) no momento")
        rel.append("-" * 100)
        if not self.estrelas_hits:
            rel.append("(nenhuma conjunção/oposição dentro do orbe configurado)")
        else:
            for h in self.estrelas_hits:
                alvo_label = f"{h['alvo']}" + (" (PT)" if h['alvo_tipo'] == 'PT' else "")
                rel.append(
                    f"{h['nome']} – {h['const']} – ({h['posE']} {h['sigE']}) {h['asp']} "
                    f"{alvo_label} ({h['posA']} {h['sigA']}) – orbe: {h['orbe']:.3f}º"
                )

        rel.append("")
        rel.append("=" * 100)
        rel.append("LEGENDA DE SIGLAS")
        rel.append("=" * 100)
        rel.append("")
        rel.append("PLANETAS:")
        rel.append("  SOL=Sol  LUA=Lua  MER=Mercúrio  VEN=Vênus  MAR=Marte")
        rel.append("  JUP=Júpiter  SAT=Saturno  URA=Urano  NET=Netuno  PLU=Plutão  TNN=Nó Lunar")
        rel.append("")
        rel.append("PONTOS FIXOS:")
        rel.append("  ASC=Ascendente  MC=Meio do Céu  FOR=Fortuna")
        rel.append("")
        rel.append("SIGNOS ZODIACAIS:")
        rel.append("  AR=Áries  TA=Touro  GE=Gêmeos  CA=Câncer  LE=Leão  VI=Virgem")
        rel.append("  LI=Libra  SC=Escorpião  SG=Sagitário  CP=Capricórnio  AQ=Aquário  PI=Peixes")
        rel.append("")
        rel.append("ASPECTOS:")
        rel.append("  CJN=Conjunção (0°)  OPO=Oposição (180°)  TRI=Trígono (120°)")
        rel.append("  SQR=Quadratura (90°)  SXT=Sextil (60°)  QCX=Quincúncio (150°)")
        rel.append("  SSQ=Semisextil (45°)  SQQ=Sesquiquadratura (135°)")
        rel.append("")
        rel.append("MOVIMENTO:")
        rel.append("  DIR=Direto  RET=Retrógrado")
        rel.append("")
        rel.append("TIPOS DE ASPECTO:")
        rel.append("  [P-P]=Planeta-Planeta  [P-PT]=Planeta-Ponto Fixo  [PT-PT]=Ponto Fixo-Ponto Fixo")
        rel.append("")
        rel.append("=" * 100)
        rel.append("")
        rel.append("ASTRO-ANALISE")
        rel.append("PROGRAMA FEITO POR ADONIS SALIBA (Out 2025)")
        rel.append("(uso gratuito e franqueado)")
        rel.append("")
        rel.append("Para analise do mapa horario por IA:")
        rel.append("https://chatgpt.com/g/g-EumgPewMI-astrologia-horaria-guia")
        rel.append("")
        rel.append("=" * 100)

        return "
".join(rel)


# --------------------------- Flask: UI e endpoints --------------------------- #

@app.route('/')
def index():
    now = datetime.utcnow()
    timezone_padrao = -3
    hora_ajustada = (now.hour + timezone_padrao + 24) % 24
    html = '''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mapa Astral</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;padding:20px}
.container{max-width:680px;margin:0 auto;background:white;border-radius:12px;padding:25px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}
h1{text-align:center;color:#333;margin-bottom:18px;font-size:24px}
fieldset{border:1px solid #ddd;border-radius:8px;padding:12px;margin-bottom:15px}
legend{padding:0 8px;color:#667eea;font-weight:bold;font-size:13px}
input,select{padding:5px;margin:3px 0;border:1px solid #ddd;border-radius:4px;font-size:11px}
label{font-size:11px;color:#555;display:block;margin-top:4px;margin-bottom:2px}
.row{display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-bottom:8px}
.row3{display:grid;grid-template-columns:60px 60px 60px 45px;gap:3px;margin-bottom:8px}
.row2{display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:6px;margin-bottom:8px}
.rowtz{display:grid;grid-template-columns:100px 1fr 140px;gap:6px;margin-bottom:8px}
button{width:100%;padding:8px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:4px;cursor:pointer;font-weight:bold;font-size:12px}
button:hover{transform:translateY(-2px)}
.resultado{margin-top:20px;padding:15px;background:#f0f9ff;border-radius:8px;display:none;max-height:500px;overflow-y:auto}
.resultado pre{font-family:monospace;font-size:10px;color:#1e3a8a}
.loading{display:none;text-align:center;color:#667eea;font-weight:bold;font-size:12px}
#modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:1000;align-items:center;justify-content:center}
#modal>div{background:white;padding:20px;border-radius:8px;width:90%;max-width:400px}
#cidades-list{max-height:200px;overflow-y:auto;border:1px solid #ddd;border-radius:4px}
.cidade-item{padding:8px;border-bottom:1px solid #eee;cursor:pointer;font-size:11px}
.cidade-item:hover{background:#f0f9ff}
.btn-copy{margin-top:10px;width:auto;display:inline-block;padding:6px 12px;font-size:11px}
</style>
</head>
<body>
<div class="container">
<h1>Mapa Astral Online</h1>
<form id="f">
<fieldset>
<legend>Identificacao</legend>
<input type="text" id="nome" value="Mapa do Momento" required style="width:100%">
<label>Dia / Mes / Ano</label>
<div class="row">
<input type="number" id="dia" min="1" max="31" value="''' + str(now.day) + '''" required>
<input type="number" id="mes" min="1" max="12" value="''' + str(now.month) + '''" required>
<input type="number" id="ano" value="''' + str(now.year) + '''" required>
</div>
<label>Hora / Min / Seg (Hora Local)</label>
<div class="row">
<input type="number" id="hora" min="0" max="23" value="''' + str(hora_ajustada) + '''" required>
<input type="number" id="minuto" min="0" max="59" value="''' + str(now.minute) + '''" required>
<input type="number" id="segundo" min="0" max="59" value="''' + str(now.second) + '''" required>
</div>
</fieldset>
<fieldset>
<legend>Localizacao</legend>
<div class="row2">
<input type="text" id="cidade" value="Brasilia" required placeholder="Cidade">
<input type="text" id="estado" value="DF" required placeholder="Estado">
<input type="text" id="pais" value="Brasil" required placeholder="Pais">
<button type="button" onclick="abrirBusca()" style="width:auto;padding:5px 10px">Buscar</button>
</div>
<label>Latitude ... graus  minutos  segundos</label>
<div class="row3">
<input type="number" id="latg" min="0" max="90" value="15" required>
<input type="number" id="latm" min="0" max="59" value="46" required>
<input type="number" id="lats" min="0" max="59" value="12" required>
<select id="lath" style="width:100%"><option>N</option><option selected>S</option></select>
</div>
<label>Longitude ... graus minutos segundos</label>
<div class="row3">
<input type="number" id="long" min="0" max="180" value="47" required>
<input type="number" id="lonm" min="0" max="59" value="55" required>
<input type="number" id="lons" min="0" max="59" value="12" required>
<select id="lonh" style="width:100%"><option>E</option><option selected>W</option></select>
</div>
<label>Zona de Tempo (UTC)</label>
<div class="rowtz">
<input type="number" id="tz" step="0.5" value="-3" required style="width:100%">
<div></div>
<label style="align-self:center">Orbe Estrelas (°)</label>
<input type="text" id="orbeEstrelas" value="0.10" style="width:100px" title="Orbe para CJN/OPO com estrelas fixas">
</div>
<label>Casas Terrestres</label>
<select id="houseSys" style="width:100%">
<option>Regiomontanus</option>
<option>Placidus</option>
<option>Campanus</option>
<option>Koch</option>
<option>Alcabitius</option>
<option>Porphyry</option>
<option>Whole Sign</option>
<option>Equal</option>
</select>
</fieldset>
<button type="submit">CALCULAR</button>
</form>
<div class="loading" id="load">Calculando...</div>
<div class="resultado" id="res"><pre id="txt"></pre><button class="btn-copy" onclick="copiarResultado()">Copiar Texto</button></div>
</div>

<div id="modal"><div>
<h3 style="font-size:14px;margin-bottom:10px">Buscar Cidade</h3>
<input type="text" id="search" placeholder="Digite a cidade..." style="width:100%;padding:8px;margin:10px 0;border:1px solid #ddd;border-radius:4px;font-size:12px">
<div id="cidades-list"></div>
<button onclick="document.getElementById('modal').style.display='none'" style="margin-top:10px;padding:6px">Fechar</button>
</div></div>

<script>
function dmsToDecimal(g, m, s, h) {
  let d = Math.abs(g) + Math.abs(m)/60 + Math.abs(s)/3600;
  return (h == 'S' || h == 'W') ? -d : d;
}

function copiarResultado() {
  let txt = document.getElementById('txt').textContent;
  navigator.clipboard.writeText(txt).then(function() {
    alert('Texto copiado para memoria!');
  });
}

function abrirBusca() {
  let cidadeAtual = document.getElementById('cidade').value;
  document.getElementById('search').value = cidadeAtual;
  document.getElementById('modal').style.display = 'flex';
  document.getElementById('search').focus();
}

function atualizarHoraParaTimeZone() {
  let tz = parseFloat(document.getElementById('tz').value);
  let now = new Date();
  let hora_utc = now.getUTCHours();
  let minuto_utc = now.getUTCMinutes();
  let segundo_utc = now.getUTCSeconds();
  let nova_hora = (hora_utc + tz + 24) % 24;
  document.getElementById('hora').value = Math.floor(nova_hora);
  document.getElementById('minuto').value = minuto_utc;
  document.getElementById('segundo').value = segundo_utc;
}

document.getElementById('search').addEventListener('input', async function(e) {
  let q = e.target.value;
  if (q.length < 2) {
    document.getElementById('cidades-list').innerHTML = '';
    return;
  }
  let r = await fetch('/api/cidades?q=' + encodeURIComponent(q));
  let c = await r.json();
  document.getElementById('cidades-list').innerHTML = '';
  c.forEach(function(d) {
    let div = document.createElement('div');
    div.className = 'cidade-item';
    div.textContent = d.city + ', ' + d.state + ' - ' + d.country;
    div.onclick = function() {
      document.getElementById('cidade').value = d.city;
      document.getElementById('estado').value = d.state;
      document.getElementById('pais').value = d.country;
      let latD = Math.abs(d.lat);
      let latG = Math.floor(latD);
      let latM = Math.floor((latD - latG) * 60);
      let latS = Math.round(((latD - latG) * 60 - latM) * 60);
      document.getElementById('latg').value = latG;
      document.getElementById('latm').value = latM;
      document.getElementById('lats').value = latS;
      document.getElementById('lath').value = (d.lat < 0 ? 'S' : 'N');
      let lonD = Math.abs(d.lon);
      let lonG = Math.floor(lonD);
      let lonM = Math.floor((lonD - lonG) * 60);
      let lonS = Math.round(((lonD - lonG) * 60 - lonM) * 60);
      document.getElementById('long').value = lonG;
      document.getElementById('lonm').value = lonM;
      document.getElementById('lons').value = lonS;
      document.getElementById('lonh').value = (d.lon < 0 ? 'W' : 'E');
      document.getElementById('tz').value = d.tz;
      atualizarHoraParaTimeZone();
      document.getElementById('modal').style.display = 'none';
    };
    document.getElementById('cidades-list').appendChild(div);
  });
});

document.getElementById('f').addEventListener('submit', async function(e) {
  e.preventDefault();
  let lat = dmsToDecimal(parseInt(document.getElementById('latg').value), 
                         parseInt(document.getElementById('latm').value), 
                         parseInt(document.getElementById('lats').value), 
                         document.getElementById('lath').value);
  let lon = dmsToDecimal(parseInt(document.getElementById('long').value), 
                         parseInt(document.getElementById('lonm').value), 
                         parseInt(document.getElementById('lons').value), 
                         document.getElementById('lonh').value);
  let orbeEst = document.getElementById('orbeEstrelas').value.replace(',', '.');
  let dados = {
    nome: document.getElementById('nome').value,
    dia: parseInt(document.getElementById('dia').value),
    mes: parseInt(document.getElementById('mes').value),
    ano: parseInt(document.getElementById('ano').value),
    hora: parseInt(document.getElementById('hora').value),
    minuto: parseInt(document.getElementById('minuto').value),
    segundo: parseInt(document.getElementById('segundo').value),
    latitude: lat,
    longitude: lon,
    timezone: parseFloat(document.getElementById('tz').value),
    cidade: document.getElementById('cidade').value,
    estado: document.getElementById('estado').value,
    pais: document.getElementById('pais').value,
    houseSys: document.getElementById('houseSys').value,
    estrelas_orbe: parseFloat(orbeEst)
  };
  document.getElementById('load').style.display = 'block';
  document.getElementById('res').style.display = 'none';
  let res = await fetch('/api/calcular', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(dados)
  });
  let j = await res.json();
  document.getElementById('load').style.display = 'none';
  if (j.status == 'ok') {
    document.getElementById('txt').textContent = j.relatorio;
    document.getElementById('res').style.display = 'block';
  } else {
    alert('Erro: ' + j.msg);
  }
});
</script>
</body>
</html>'''
    return html


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
                        except Exception:
                            pass
        except Exception:
            pass
    return jsonify(result)


@app.route('/api/calcular', methods=['POST'])
def calcular():
    try:
        d = request.json
        m = MapaAstral(
            d.get('nome', 'Mapa'), int(d['dia']), int(d['mes']), int(d['ano']),
            int(d['hora']), int(d['minuto']), int(d['segundo']),
            float(d['latitude']), float(d['longitude']), float(d['timezone']),
            d.get('cidade', ''), d.get('estado', ''), d.get('pais', ''),
            d.get('houseSys', 'Regiomontanus'),
            float(d.get('estrelas_orbe', 0.10))
        )
        return jsonify({'status': 'ok', 'relatorio': m.gerar_relatorio()})
    except Exception as e:
        return jsonify({'status': 'erro', 'msg': str(e)}), 400


if __name__ == '__main__':
    app.run(debug=True)
