< !DOCTYPE
html >
< html
lang = "pt-BR" >
< head >
< meta
charset = "UTF-8" >
< meta
name = "viewport"
content = "width=device-width, initial-scale=1.0" >
< title > Mapa
Astral
Online < / title >
< link
rel = "stylesheet"
href = "style.css" >
< / head >
< body >
< div


class ="container" >

< h1 >🌙 Mapa
Astral
Online < / h1 >

< form
id = "mapForm" >
< fieldset >
< legend > Identificação < / legend >
< input
type = "text"
id = "nome"
placeholder = "Nome completo"
required >
< input
type = "text"
id = "cidade"
placeholder = "Cidade"
required >
< input
type = "text"
id = "estado"
placeholder = "Estado"
required >
< / fieldset >

< fieldset >
< legend > Data
e
Hora
de
Nascimento < / legend >
< div


class ="row" >

< input
type = "number"
id = "dia"
min = "1"
max = "31"
placeholder = "Dia"
required >
< input
type = "number"
id = "mes"
min = "1"
max = "12"
placeholder = "Mês"
required >
< input
type = "number"
id = "ano"
min = "1900"
max = "2100"
placeholder = "Ano"
required >
< / div >
< div


class ="row" >

< input
type = "number"
id = "hora"
min = "0"
max = "23"
placeholder = "Hora"
required >
< input
type = "number"
id = "minuto"
min = "0"
max = "59"
placeholder = "Minuto"
required >
< input
type = "number"
id = "segundo"
min = "0"
max = "59"
placeholder = "Segundo"
required >
< / div >
< / fieldset >

< fieldset >
< legend > Localização < / legend >
< input
type = "number"
id = "latitude"
step = "0.01"
placeholder = "Latitude"
required >
< input
type = "number"
id = "longitude"
step = "0.01"
placeholder = "Longitude"
required >
< input
type = "number"
id = "timezone"
step = "0.5"
placeholder = "UTC (ex: -3)"
required >
< / fieldset >

< button
type = "submit"
id = "btnCalc" > CALCULAR
MAPA
ASTRAL < / button >
< / form >

< div
id = "loading"


class ="loading" style="display:none;" >


Calculando
mapa
astral... ⏳
< / div >

< div
id = "resultado"


class ="resultado" style="display:none;" >

< button
type = "button"


class ="close-btn" onclick="fecharResultado()" > ✕ < / button >

< pre
id = "textoResultado" > < / pre >
< / div >

< div
id = "erro"


class ="erro" style="display:none;" >

< button
type = "button"


class ="close-btn" onclick="fecharErro()" > ✕ < / button >

< p
id = "textoErro" > < / p >
< / div >
< / div >

< script >
// Buscar
cidades
automaticamente
document.getElementById('cidade').addEventListener('input', async (e) = > {
if (e.target.value.length < 2)
return;

const
res = await fetch(` / api / cidades?q =${e.target.value}
`);
const
cidades = await res.json();

if (cidades.length > 0) {
const cidade = cidades[0];
document.getElementById('latitude').value = cidade.lat.toFixed(2);
document.getElementById('longitude').value = cidade.lon.toFixed(2);
document.getElementById('timezone').value = cidade.tz.toFixed(1);
}
});

// Enviar
formulário
document.getElementById('mapForm').addEventListener('submit', async (e) = > {
e.preventDefault();

const
dados = {
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
};

document.getElementById('loading').style.display = 'block';
document.getElementById('resultado').style.display = 'none';
document.getElementById('erro').style.display = 'none';

try {
const res = await fetch('/api/calcular', {
method: 'POST',
headers: {'Content-Type': 'application/json'},
body: JSON.stringify(dados)
});

const
json = await res.json();
document.getElementById('loading').style.display = 'none';

if (json.status === 'ok')
{
    document.getElementById('textoResultado').textContent = json.relatorio;
document.getElementById('resultado').style.display = 'block';
} else {
    document.getElementById('textoErro').textContent = json.msg | | 'Erro desconhecido';
document.getElementById('erro').style.display = 'block';
}
} catch(e)
{
    document.getElementById('loading').style.display = 'none';
document.getElementById('textoErro').textContent = 'Erro de conexão: ' + e.message;
document.getElementById('erro').style.display = 'block';
}
});

function
fecharResultado()
{
    document.getElementById('resultado').style.display = 'none';
}

function
fecharErro()
{
    document.getElementById('erro').style.display = 'none';
}
< / script >
    < / body >
        < / html >