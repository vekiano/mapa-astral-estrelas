from flask import Flask, request, jsonify, send_from_directory
import sys
import os
from datetime import datetime, timedelta

# Importar sua classe MapaAstral (adapte conforme necessário)
try:
    import swisseph as swe
except:
    pass

app = Flask(__name__, static_folder='../public', static_url_path='')


# Seu código MapaAstral aqui (copie de mapa_ah.py)
# ... (toda a classe MapaAstral, funções auxiliares, etc)

@app.route('/')
def index():
    return send_from_directory('../public', 'index.html')


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

        relatorio = mapa.gerar_relatorio(incluir_transitos=True)

        return jsonify({
            'status': 'ok',
            'relatorio': relatorio,
            'planetas_count': len(mapa.planetas),
            'aspectos_count': len(mapa.aspectos_natais),
            'transitos_count': len(mapa.transitos)
        })
    except Exception as e:
        return jsonify({'status': 'erro', 'msg': str(e)}), 400


@app.route('/api/cidades', methods=['GET'])
def buscar_cidades():
    """Busca cidades no CidMundo.txt"""
    q = request.args.get('q', '').lower()
    try:
        # Caminho relativo funciona na Vercel
        cidmundo_path = os.path.join(os.path.dirname(__file__), '..', 'CidMundo.txt')

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


if __name__ == '__main__':
    app.run(debug=True)