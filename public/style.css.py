* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    padding: 20px;
}

.container {
    max-width: 600px;
    margin: 0 auto;
    background: white;
    border-radius: 12px;
    padding: 40px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

h1 {
    text-align: center;
    color: #333;
    margin-bottom: 30px;
    font-size: 28px;
}

fieldset {
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 15px;
    margin-bottom: 20px;
}

legend {
    padding: 0 10px;
    color: #667eea;
    font-weight: 600;
}

input {
    width: 100%;
    padding: 10px;
    margin: 8px 0;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 14px;
}

input:focus {
    outline: none;
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 10px;
}

.row input {
    margin: 8px 0;
}

button[type="submit"] {
    width: 100%;
    padding: 12px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.2s;
}

button[type="submit"]:hover {
    transform: translateY(-2px);
}

button[type="submit"]:active {
    transform: translateY(0);
}

.loading {
    text-align: center;
    padding: 20px;
    color: #667eea;
    font-weight: 600;
}

.resultado, .erro {
    margin-top: 30px;
    padding: 20px;
    border-radius: 8px;
    position: relative;
}

.resultado {
    background: #f0f9ff;
    border: 1px solid #bfdbfe;
}

.resultado pre {
    font-family: 'Courier New', monospace;
    font-size: 12px;
    overflow-x: auto;
    max-height: 400px;
    overflow-y: auto;
    color: #1e3a8a;
}

.erro {
    background: #fef2f2;
    border: 1px solid #fecaca;
}

.erro p {
    color: #991b1b;
    font-weight: 500;
}

.close-btn {
    position: absolute;
    top: 10px;
    right: 10px;
    background: none;
    border: none;
    font-size: 20px;
    cursor: pointer;
    color: #999;
}

.close-btn:hover {
    color: #333;
}

@media (max-width: 600px) {
    .container {
        padding: 20px;
    }

    h1 {
        font-size: 22px;
    }

    .row {
        grid-template-columns: 1fr;
    }
}