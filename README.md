# WBS Hub

Gerador de Work Breakdown Structure para Monday.com. Substitui os forms do Monday + automação n8n por uma interface única, configurável e de fácil manutenção.

## Estrutura

```
wbs-hub/
├── app.py                 # Aplicação Streamlit principal
├── config.yaml            # Configurações gerais (endpoint Make, etc)
├── requirements.txt       # Dependências Python
├── templates/             # Templates de WBS
│   ├── wbs_eletrico.yaml
│   ├── wbs_mecanico.yaml
│   └── wbs_aquisicao.yaml
└── utils/
    └── wbs_logic.py       # Lógica de quebra em percentuais
```

## Instalação

```bash
# Clone ou copie a pasta wbs-hub
cd wbs-hub

# Crie um ambiente virtual (opcional mas recomendado)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Instale as dependências
pip install -r requirements.txt
```

## Configuração

### 1. Endpoint Make

Edite `config.yaml` e substitua o endpoint:

```yaml
make_endpoint: "https://hook.us1.make.com/SEU_ENDPOINT_REAL"
```

Ou configure diretamente na interface (sidebar).

### 2. Payload esperado pelo Make

O hub envia um POST para cada tarefa com o seguinte JSON:

```json
{
  "tarefa": "010 - 1. Desenvolver arquitetura elétrica - 50%",
  "projeto": "01058 - Montagem de segmento de bomba VB - BBRAUN",
  "wbs_type": "eletrico"
}
```

Configure seu cenário Make para:
1. Receber o webhook
2. Usar `wbs_type` para rotear/categorizar se necessário
3. Criar o item no Monday usando `tarefa` como nome e `projeto` para vincular

## Uso

```bash
# Execute o Streamlit
streamlit run app.py
```

1. Selecione o tipo de WBS (elétrico, mecânico, etc)
2. Preencha o código do WBS (ex: "010")
3. Preencha o projeto vinculado
4. Marque as tarefas desejadas e defina os dias
5. Confira o preview
6. Clique em "Criar Tarefas"

## Adicionando novos templates

Crie um novo arquivo em `templates/` seguindo a estrutura:

```yaml
# templates/wbs_novo.yaml

nome: "WBS Novo Tipo"
wbs_type: "novo"  # identificador único
descricao: "Descrição do template"

tarefas:
  - id: 1
    nome: "Primeira tarefa"
    obrigatoria: false
    dias_default: 2
  
  - id: 2
    nome: "Segunda tarefa"
    obrigatoria: false
    dias_default: 1
  
  # ... adicione mais tarefas
```

O novo template aparecerá automaticamente na interface ao reiniciar o app.

## Lógica de Percentuais

A quebra de dias em percentuais funciona assim:

| Dias | Tarefas geradas |
|------|-----------------|
| 1    | 100%            |
| 2    | 50%, 100%       |
| 3    | 33%, 67%, 100%  |
| 4    | 25%, 50%, 75%, 100% |

Isso replica a lógica original do n8n.

## Diferenças do fluxo antigo

| Antes (Monday + n8n + Make) | Agora (Streamlit + Make) |
|-----------------------------|--------------------------|
| Form limitado do Monday     | Interface flexível       |
| Mapeamento hardcoded no n8n | Templates em YAML        |
| Difícil adicionar campos    | Edita YAML e pronto      |
| 3 ferramentas para manter   | 1 ferramenta + Make      |

## Troubleshooting

**Erro de conexão com Make:**
- Verifique se o endpoint está correto
- Confirme que o cenário Make está ativo
- Aumente o timeout em `config.yaml` se necessário

**Tarefas não aparecem no Monday:**
- Confira o cenário Make (logs de execução)
- Verifique se o `wbs_type` está sendo roteado corretamente

**Novo template não aparece:**
- Confira se o arquivo está em `templates/` com extensão `.yaml`
- Verifique se o YAML está válido (sintaxe correta)
- Reinicie o Streamlit
