"""Categorias e termos de busca usados pelo PlayStore Radar Ultra."""
from __future__ import annotations

from typing import Dict, List, Tuple

# code, nome amigável, termo de fallback para search()
CATEGORIAS_APPS: Dict[int, Tuple[str, str, str]] = {
    1: ("ANDROID_WEAR", "Android Wear", "Wear OS smartwatch apps"),
    2: ("ART_AND_DESIGN", "Arte e Design", "arte design desenho pintura"),
    3: ("AUTO_AND_VEHICLES", "Automóveis e Veículos", "carros veículos manutenção auto"),
    4: ("BEAUTY", "Beleza", "beleza maquiagem skincare"),
    5: ("BOOKS_AND_REFERENCE", "Livros e Referências", "livros leitura referência dicionário"),
    6: ("BUSINESS", "Negócios", "negócios vendas gestão empresa"),
    7: ("COMICS", "Quadrinhos", "quadrinhos manga comics"),
    8: ("COMMUNICATION", "Comunicação", "mensagens chamadas comunicação"),
    9: ("DATING", "Encontros", "relacionamento encontros namoro"),
    10: ("EDUCATION", "Educação", "educação cursos estudar aprender"),
    11: ("ENTERTAINMENT", "Entretenimento", "streaming entretenimento filmes séries"),
    12: ("EVENTS", "Eventos", "eventos ingressos agenda"),
    13: ("FINANCE", "Finanças", "finanças banco dinheiro investimento"),
    14: ("FOOD_AND_DRINK", "Gastronomia", "comida delivery receita restaurante"),
    15: ("HEALTH_AND_FITNESS", "Saúde e Fitness", "fitness saúde treino dieta"),
    16: ("HOUSE_AND_HOME", "Casa e Decoração", "casa decoração imóveis"),
    17: ("LIBRARIES_AND_DEMO", "Bibliotecas e Demonstrações", "bibliotecas demo android"),
    18: ("LIFESTYLE", "Estilo de Vida", "lifestyle rotina hábitos"),
    19: ("MAPS_AND_NAVIGATION", "Mapas e Navegação", "mapas gps navegação trânsito"),
    20: ("MEDICAL", "Medicina", "medicina saúde médico remédio"),
    21: ("MUSIC_AND_AUDIO", "Música e Áudio", "música áudio podcast player"),
    22: ("NEWS_AND_MAGAZINES", "Notícias e Revistas", "notícias jornal revista"),
    23: ("PARENTING", "Paternidade", "bebê gravidez maternidade paternidade"),
    24: ("PERSONALIZATION", "Personalização", "wallpaper launcher tema ícones"),
    25: ("PHOTOGRAPHY", "Fotografia", "foto câmera editor imagem"),
    26: ("PRODUCTIVITY", "Produtividade", "produtividade tarefas notas calendário"),
    27: ("SHOPPING", "Compras", "compras ofertas marketplace"),
    28: ("SOCIAL", "Redes Sociais", "rede social social media"),
    29: ("SPORTS", "Esportes", "esportes futebol placar"),
    30: ("TOOLS", "Ferramentas", "ferramentas utilitários android"),
    31: ("TRAVEL_AND_LOCAL", "Viagens e Localização", "viagem hotel passagem turismo"),
    32: ("VIDEO_PLAYERS", "Reprodutores de Vídeo", "vídeo player streaming"),
    33: ("WEATHER", "Clima", "clima tempo previsão"),
}

CATEGORIAS_JOGOS: Dict[int, Tuple[str, str, str]] = {
    1: ("GAME", "Jogos em Geral", "jogos android"),
    2: ("GAME_ACTION", "Jogos de Ação", "jogos ação"),
    3: ("GAME_ADVENTURE", "Jogos de Aventura", "jogos aventura"),
    4: ("GAME_ARCADE", "Jogos Arcade", "jogos arcade"),
    5: ("GAME_BOARD", "Jogos de Tabuleiro", "jogos tabuleiro board games"),
    6: ("GAME_CARD", "Jogos de Cartas", "jogos cartas card games"),
    7: ("GAME_CASINO", "Jogos de Cassino", "jogos cassino slots"),
    8: ("GAME_CASUAL", "Jogos Casuais", "jogos casuais"),
    9: ("GAME_EDUCATIONAL", "Jogos Educacionais", "jogos educacionais"),
    10: ("GAME_MUSIC", "Jogos Musicais", "jogos musicais ritmo"),
    11: ("GAME_PUZZLE", "Jogos de Quebra-Cabeça", "jogos puzzle quebra cabeça"),
    12: ("GAME_RACING", "Jogos de Corrida", "jogos corrida carros"),
    13: ("GAME_ROLE_PLAYING", "Jogos de RPG", "jogos rpg"),
    14: ("GAME_SIMULATION", "Jogos de Simulação", "jogos simulação"),
    15: ("GAME_SPORTS", "Jogos Esportivos", "jogos esportivos"),
    16: ("GAME_STRATEGY", "Jogos de Estratégia", "jogos estratégia"),
    17: ("GAME_TRIVIA", "Jogos de Trivia", "jogos perguntas trivia quiz"),
    18: ("GAME_WORD", "Jogos de Palavras", "jogos palavras caça palavras"),
    19: ("FAMILY", "Família", "jogos família infantil"),
}


SUBCATEGORIAS: Dict[str, List[Tuple[str, str, str]]] = {
    # ---- Apps ----
    "ANDROID_WEAR": [
        ("MOSTRADORES", "Mostradores e Watchfaces", "watchface relógio mostrador wear os"),
        ("FITNESS_WEAR", "Fitness no Pulso", "treino monitor cardíaco wear os"),
        ("NOTIF_WEAR", "Notificações e Produtividade", "notificações produtividade wear os"),
        ("GAMES_WEAR", "Mini Apps e Jogos", "mini jogos apps wear os"),
    ],
    "ART_AND_DESIGN": [
        ("DESENHO", "Desenho e Ilustração", "desenho ilustração arte digital"),
        ("EDICAO_GRAFICA", "Edição Gráfica", "editor gráfico design logotipo"),
        ("COLORIR", "Livros de Colorir", "livro colorir pintar números"),
        ("FONTES", "Fontes e Tipografia", "fontes tipografia caligrafia"),
    ],
    "AUTO_AND_VEHICLES": [
        ("MANUTENCAO", "Manutenção e Diagnóstico", "diagnóstico obd2 manutenção carro"),
        ("COMBUSTIVEL", "Combustível e Postos", "preço combustível posto gasolina"),
        ("HABILITACAO", "Simulados de Habilitação", "simulado detran cnh"),
        ("CATALOGO_VEICULOS", "Catálogo e Avaliação de Veículos", "tabela fipe avaliação veículo"),
    ],
    "BEAUTY": [
        ("MAQUIAGEM", "Maquiagem Virtual", "maquiagem virtual provador"),
        ("SKINCARE", "Skincare e Rotina", "skincare rotina pele"),
        ("CABELO", "Cabelo e Penteados", "cabelo penteado tutorial"),
        ("AGENDAMENTO_SALAO", "Agendamento de Salão", "agendamento salão beleza"),
    ],
    "BOOKS_AND_REFERENCE": [
        ("EBOOKS", "Leitores de Ebook", "leitor ebook epub"),
        ("DICIONARIOS", "Dicionários e Tradução", "dicionário tradutor idiomas"),
        ("RESUMOS", "Resumos e Estudos", "resumo livro estudo"),
        ("RELIGIOSO", "Bíblia e Textos Religiosos", "bíblia estudo religioso"),
    ],
    "BUSINESS": [
        ("CRM", "CRM e Vendas", "crm vendas clientes"),
        ("NOTA_FISCAL", "Nota Fiscal e Contabilidade", "nota fiscal contabilidade mei"),
        ("RH", "RH e Gestão de Equipe", "rh gestão equipe ponto"),
        ("ERP_PEQUENO", "ERP para Pequenos Negócios", "erp estoque pequeno negócio"),
    ],
    "COMICS": [
        ("MANGA", "Mangás", "mangá leitor japonês"),
        ("HQ_NACIONAL", "HQs Nacionais", "quadrinho nacional turma"),
        ("WEBTOON", "Webtoons", "webtoon coreano vertical"),
        ("LEITOR_CBR", "Leitores CBR/CBZ", "leitor cbr cbz quadrinho"),
    ],
    "COMMUNICATION": [
        ("SMS_CHAMADAS", "SMS e Chamadas", "sms chamadas discador"),
        ("VIDEOCHAMADA", "Videochamadas", "videochamada reunião"),
        ("EMAIL", "Clientes de E-mail", "email cliente caixa entrada"),
        ("VPN_SEGURANCA", "VPN e Privacidade", "vpn privacidade mensagens"),
    ],
    "DATING": [
        ("PAQUERA_CASUAL", "Paquera Casual", "paquera bate papo encontro casual"),
        ("RELACIONAMENTO_SERIO", "Relacionamento Sério", "relacionamento sério namoro"),
        ("NICHO_LGBT", "Encontros Nichados", "encontro lgbt maduro nicho"),
        ("AMIZADE", "Amizade e Social", "amizade novos amigos"),
    ],
    "EDUCATION": [
        ("IDIOMAS", "Aprender Idiomas", "aprender inglês idiomas app"),
        ("CONCURSOS", "Concursos e Vestibular", "concurso vestibular enem"),
        ("INFANTIL_EDU", "Educação Infantil", "alfabetização crianças jogo educativo"),
        ("CURSOS_ONLINE", "Cursos Online", "curso online aula vídeo"),
    ],
    "ENTERTAINMENT": [
        ("STREAMING_VIDEO", "Streaming de Vídeo", "streaming filme série"),
        ("MEMES_HUMOR", "Memes e Humor", "meme humor piada"),
        ("HOROSCOPO", "Horóscopo e Tarot", "horóscopo tarot signo"),
        ("FOFOCA_CELEBS", "Fofoca e Celebridades", "fofoca celebridade fama"),
    ],
    "EVENTS": [
        ("INGRESSOS", "Ingressos e Shows", "ingresso show evento"),
        ("AGENDA_LOCAL", "Agenda Local", "agenda cidade evento local"),
        ("CASAMENTO", "Planejamento de Casamento", "casamento planejamento festa"),
        ("CONFERENCIAS", "Conferências e Networking", "conferência networking profissional"),
    ],
    "FINANCE": [
        ("BANCO_DIGITAL", "Banco Digital", "banco digital conta"),
        ("INVESTIMENTOS", "Investimentos", "investimento bolsa renda fixa"),
        ("CONTROLE_GASTOS", "Controle de Gastos", "controle gastos orçamento planilha"),
        ("EMPRESTIMO", "Empréstimo e Crédito", "empréstimo crédito score"),
    ],
    "FOOD_AND_DRINK": [
        ("DELIVERY", "Delivery de Comida", "delivery comida pedido"),
        ("RECEITAS", "Receitas", "receita culinária cozinhar"),
        ("DIETA_NUTRI", "Dieta e Nutrição", "dieta nutrição calorias"),
        ("RESERVA_RESTAURANTE", "Reserva de Restaurante", "reserva restaurante mesa"),
    ],
    "HEALTH_AND_FITNESS": [
        ("TREINO_ACADEMIA", "Treino e Academia", "treino academia musculação"),
        ("CORRIDA_CICLISMO", "Corrida e Ciclismo", "corrida ciclismo pace"),
        ("MEDITACAO", "Meditação e Sono", "meditação sono relaxamento"),
        ("CICLO_MENSTRUAL", "Ciclo Menstrual e Saúde da Mulher", "ciclo menstrual saúde mulher"),
    ],
    "HOUSE_AND_HOME": [
        ("DECORACAO", "Decoração e Design de Interiores", "decoração design interiores planta baixa"),
        ("IMOVEIS", "Imóveis", "imóveis aluguel comprar casa"),
        ("JARDINAGEM", "Jardinagem", "jardinagem plantas cuidado"),
        ("SERVICOS_CASA", "Serviços para Casa", "serviço encanador eletricista diarista"),
    ],
    "LIBRARIES_AND_DEMO": [
        ("SDK_DEMO", "Demos de SDK", "demo sdk biblioteca"),
        ("WALLPAPER_ENGINE", "Motores de Wallpaper", "motor wallpaper live"),
        ("FRAMEWORK_TESTE", "Frameworks de Teste", "framework teste app demo"),
        ("COMPONENTES_UI", "Componentes de UI", "componente ui biblioteca android"),
    ],
    "LIFESTYLE": [
        ("HABITOS", "Hábitos e Rotina", "hábito rotina produtividade pessoal"),
        ("ASTROLOGIA", "Astrologia e Espiritualidade", "astrologia espiritualidade signo"),
        ("MINIMALISMO", "Minimalismo e Organização", "minimalismo organização casa"),
        ("MODA_ESTILO", "Moda e Estilo", "moda estilo look"),
    ],
    "MAPS_AND_NAVIGATION": [
        ("GPS_TRANSITO", "GPS e Trânsito", "gps trânsito rota"),
        ("TRANSPORTE_PUBLICO", "Transporte Público", "ônibus metrô transporte público"),
        ("RASTREAMENTO", "Rastreamento e Localização", "rastreamento localização família"),
        ("MAPAS_OFFLINE", "Mapas Offline", "mapa offline trilha"),
    ],
    "MEDICAL": [
        ("TELEMEDICINA", "Telemedicina", "telemedicina consulta online"),
        ("MEDICAMENTOS", "Controle de Medicamentos", "controle medicamento remédio lembrete"),
        ("EXAMES", "Exames e Resultados", "exame resultado laboratório"),
        ("SAUDE_MENTAL", "Saúde Mental", "saúde mental terapia psicologia"),
    ],
    "MUSIC_AND_AUDIO": [
        ("STREAMING_MUSICA", "Streaming de Música", "streaming música ouvir"),
        ("PODCAST", "Podcasts", "podcast áudio programa"),
        ("PRODUCAO_MUSICAL", "Produção Musical", "produção musical daw beat"),
        ("LETRAS_CIFRAS", "Letras e Cifras", "letra cifra música violão"),
    ],
    "NEWS_AND_MAGAZINES": [
        ("NOTICIAS_GERAL", "Notícias Gerais", "notícia jornal geral"),
        ("ESPORTIVO_NEWS", "Notícias Esportivas", "notícia esporte futebol"),
        ("REVISTAS_DIGITAIS", "Revistas Digitais", "revista digital assinatura"),
        ("AGREGADORES", "Agregadores de Conteúdo", "agregador rss notícia"),
    ],
    "PARENTING": [
        ("GRAVIDEZ", "Gravidez", "gravidez gestação semana"),
        ("BEBE", "Cuidados com Bebê", "bebê cuidado recém-nascido"),
        ("CONTROLE_PARENTAL", "Controle Parental", "controle parental filho tela"),
        ("EDUCACAO_FILHOS", "Educação dos Filhos", "educação filhos dicas pais"),
    ],
    "PERSONALIZATION": [
        ("WALLPAPERS", "Papéis de Parede", "wallpaper papel de parede"),
        ("LAUNCHERS", "Launchers", "launcher lançador tela inicial"),
        ("ICONES_TEMAS", "Ícones e Temas", "ícone tema pacote"),
        ("WIDGETS", "Widgets", "widget personalização tela"),
    ],
    "PHOTOGRAPHY": [
        ("EDICAO_FOTO", "Edição de Fotos", "editor foto filtro"),
        ("CAMERA_MANUAL", "Câmera Manual e Pro", "câmera manual profissional"),
        ("COLAGEM", "Colagem e Álbuns", "colagem álbum foto"),
        ("IA_FOTO", "Fotos com IA", "foto ia gerador avatar"),
    ],
    "PRODUCTIVITY": [
        ("NOTAS", "Notas e Anotações", "notas anotação bloco"),
        ("CALENDARIO_AGENDA", "Calendário e Agenda", "calendário agenda compromisso"),
        ("TAREFAS", "Tarefas e To-do", "tarefa lista afazeres"),
        ("ESCANER_DOC", "Scanner de Documentos", "scanner documento pdf"),
    ],
    "SHOPPING": [
        ("MARKETPLACE", "Marketplace Geral", "marketplace compra vender"),
        ("CUPONS", "Cupons e Ofertas", "cupom desconto oferta"),
        ("MODA_SHOPPING", "Moda e Vestuário", "roupa moda loja online"),
        ("SUPERMERCADO", "Supermercado e Mercado", "supermercado mercado compra online"),
    ],
    "SOCIAL": [
        ("REDES_GERAIS", "Redes Sociais Gerais", "rede social feed"),
        ("COMUNIDADES_NICHO", "Comunidades de Nicho", "comunidade nicho fórum"),
        ("STORIES_EFEMERO", "Conteúdo Efêmero", "stories efêmero vídeo curto"),
        ("ANONIMO", "Redes Anônimas", "rede social anônimo confissão"),
    ],
    "SPORTS": [
        ("PLACARES", "Placares ao Vivo", "placar ao vivo futebol"),
        ("FANTASY_GAME", "Fantasy Games", "fantasy game bolão time"),
        ("ESTATISTICAS", "Estatísticas Esportivas", "estatística esportiva jogador"),
        ("TREINO_ESPORTIVO", "Treino Esportivo", "treino esportivo técnico"),
    ],
    "TOOLS": [
        ("GERENCIADOR_ARQUIVOS", "Gerenciador de Arquivos", "gerenciador arquivo explorer"),
        ("LIMPEZA_OTIMIZACAO", "Limpeza e Otimização", "limpeza otimização memória"),
        ("VPN_TOOLS", "VPN e Segurança", "vpn segurança bloqueador anúncio"),
        ("CONVERSOR_UTILIDADES", "Conversores e Utilidades", "conversor calculadora utilidade"),
    ],
    "TRAVEL_AND_LOCAL": [
        ("PASSAGENS", "Passagens Aéreas", "passagem aérea voo"),
        ("HOSPEDAGEM", "Hospedagem", "hospedagem hotel pousada"),
        ("ROTEIROS_TURISMO", "Roteiros e Turismo", "roteiro turismo viagem"),
        ("GUIA_LOCAL", "Guia Local", "guia local cidade avaliação"),
    ],
    "VIDEO_PLAYERS": [
        ("PLAYER_LOCAL", "Players de Vídeo Local", "player vídeo local arquivo"),
        ("STREAMING_VIDEO_PLAYERS", "Apps de Streaming", "streaming assistir filme"),
        ("EDICAO_VIDEO", "Edição de Vídeo", "edição vídeo editor"),
        ("DOWNLOAD_VIDEO", "Download de Vídeo", "download vídeo baixar"),
    ],
    "WEATHER": [
        ("PREVISAO_GERAL", "Previsão Geral", "previsão tempo clima"),
        ("RADAR_CHUVA", "Radar de Chuva", "radar chuva tempo real"),
        ("CLIMA_AGRO", "Clima para Agricultura", "clima agricultura agro"),
        ("ALERTAS_CLIMATICOS", "Alertas Climáticos", "alerta clima extremo"),
    ],
    # ---- Jogos ----
    "GAME": [
        ("HIPER_CASUAL", "Hiper Casuais", "jogo hiper casual simples"),
        ("IDLE_CLICKER", "Idle e Clicker", "jogo idle clicker"),
        ("MULTIPLAYER_GERAL", "Multiplayer Geral", "jogo multiplayer online"),
        ("OFFLINE_GERAL", "Offline sem Internet", "jogo offline sem internet"),
    ],
    "GAME_ACTION": [
        ("TIRO_FPS", "Tiro e FPS", "jogo tiro fps atirador"),
        ("LUTA", "Luta", "jogo luta combate"),
        ("HACK_SLASH", "Hack and Slash", "jogo hack slash ação"),
        ("PLATAFORMA_ACAO", "Plataforma de Ação", "jogo plataforma ação"),
    ],
    "GAME_ADVENTURE": [
        ("SOBREVIVENCIA", "Sobrevivência", "jogo sobrevivência survival"),
        ("EXPLORACAO", "Exploração e Mundo Aberto", "jogo exploração mundo aberto"),
        ("NARRATIVO", "Narrativos", "jogo narrativo história"),
        ("PONTO_CLIQUE", "Ponto e Clique", "jogo ponto clique puzzle aventura"),
    ],
    "GAME_ARCADE": [
        ("RETRO_ARCADE", "Retrô e Clássicos", "jogo retrô clássico arcade"),
        ("ENDLESS_RUNNER", "Corrida Infinita", "jogo endless runner corrida infinita"),
        ("SHOOT_EM_UP", "Shoot 'em Up", "jogo shoot em up nave"),
        ("PINBALL", "Pinball", "jogo pinball fliperama"),
    ],
    "GAME_BOARD": [
        ("XADREZ_DAMAS", "Xadrez e Damas", "jogo xadrez damas"),
        ("DOMINO", "Dominó", "jogo dominó"),
        ("ECONOMICO_TABULEIRO", "Jogos Econômicos", "jogo tabuleiro econômico banco imobiliário"),
        ("CLASSICOS_TABULEIRO", "Clássicos de Tabuleiro", "jogo tabuleiro clássico família"),
    ],
    "GAME_CARD": [
        ("TRUCO_BURACO", "Truco e Buraco", "jogo truco buraco carta brasileiro"),
        ("POKER", "Pôquer", "jogo pôquer carta"),
        ("SOLITAIRE", "Paciência/Solitaire", "jogo paciência solitaire carta"),
        ("TCG_COLECIONAVEL", "Card Game Colecionável", "jogo card game colecionável tcg"),
    ],
    "GAME_CASINO": [
        ("SLOTS", "Caça-Níqueis", "jogo caça níquel slot"),
        ("BINGO", "Bingo", "jogo bingo"),
        ("ROLETA_MESA", "Roleta e Mesa", "jogo roleta mesa cassino"),
        ("LOTERIA_SIMULADA", "Loteria Simulada", "jogo loteria simulada sorteio"),
    ],
    "GAME_CASUAL": [
        ("MATCH3", "Match-3", "jogo match 3 combinar"),
        ("TIME_MANAGEMENT", "Gestão de Tempo", "jogo gestão tempo garçom restaurante"),
        ("DECORACAO_CASUAL", "Decoração e Design", "jogo decoração design casa"),
        ("HIDDEN_OBJECT", "Objetos Escondidos", "jogo objeto escondido procurar"),
    ],
    "GAME_EDUCATIONAL": [
        ("ALFABETIZACAO_JOGO", "Alfabetização", "jogo alfabetização letras crianças"),
        ("MATEMATICA_JOGO", "Matemática", "jogo matemática conta crianças"),
        ("CIENCIAS_JOGO", "Ciências", "jogo ciência aprender crianças"),
        ("IDIOMAS_JOGO", "Idiomas em Jogo", "jogo aprender idioma inglês"),
    ],
    "GAME_MUSIC": [
        ("RITMO_TAP", "Ritmo e Tap", "jogo ritmo tap música"),
        ("KARAOKE_GAME", "Karaokê", "jogo karaokê cantar"),
        ("INSTRUMENTO_VIRTUAL", "Instrumento Virtual", "jogo instrumento virtual piano bateria"),
        ("DANCA_RITMO", "Dança e Ritmo", "jogo dança ritmo movimento"),
    ],
    "GAME_PUZZLE": [
        ("LOGICA", "Lógica", "jogo lógica raciocínio"),
        ("PALAVRAS_CRUZADAS_PUZZLE", "Palavras Cruzadas", "jogo palavra cruzada"),
        ("QUEBRA_CABECA_IMAGEM", "Quebra-Cabeça de Imagem", "jogo quebra cabeça imagem puzzle"),
        ("ESCAPE_ROOM", "Escape Room", "jogo escape room fuga"),
    ],
    "GAME_RACING": [
        ("ARCADE_CORRIDA", "Corrida Arcade", "jogo corrida arcade carro"),
        ("SIMULADOR_CORRIDA", "Simulador de Corrida", "jogo simulador corrida realista"),
        ("MOTOS", "Motos", "jogo moto corrida"),
        ("KART", "Kart", "jogo kart corrida"),
    ],
    "GAME_ROLE_PLAYING": [
        ("RPG_ACAO", "RPG de Ação", "jogo rpg ação combate"),
        ("RPG_TATICO", "RPG Tático", "jogo rpg tático turnos estratégia"),
        ("RPG_GACHA", "RPG Colecionável (Gacha)", "jogo rpg gacha colecionar personagem"),
        ("RPG_VISUAL_NOVEL", "RPG de Texto/Visual Novel", "jogo rpg visual novel texto"),
    ],
    "GAME_SIMULATION": [
        ("FAZENDA_SIM", "Fazenda e Cidade", "jogo fazenda cidade simulação construir"),
        ("VIDA_SIM", "Simulação de Vida", "jogo simulação vida família"),
        ("VEICULOS_SIM", "Veículos e Direção", "jogo simulação direção caminhão ônibus"),
        ("NEGOCIOS_SIM", "Negócios e Tycoon", "jogo simulação negócio tycoon"),
    ],
    "GAME_SPORTS": [
        ("FUTEBOL", "Futebol", "jogo futebol"),
        ("BASQUETE", "Basquete", "jogo basquete"),
        ("ESPORTES_RADICAIS", "Esportes Radicais", "jogo esporte radical skate surf"),
        ("GESTAO_TIME", "Gestão de Time", "jogo gestão time técnico manager"),
    ],
    "GAME_STRATEGY": [
        ("ESTRATEGIA_TEMPO_REAL", "Estratégia em Tempo Real", "jogo estratégia tempo real batalha"),
        ("ESTRATEGIA_TURNOS", "Estratégia por Turnos", "jogo estratégia turnos tático"),
        ("TOWER_DEFENSE", "Tower Defense", "jogo tower defense torre"),
        ("CONSTRUCAO_IMPERIO", "Construção de Império", "jogo construção império guerra"),
    ],
    "GAME_TRIVIA": [
        ("QUIZ_GERAL", "Quiz Geral", "jogo quiz perguntas gerais"),
        ("TRIVIA_CULTURA", "Trivia de Cultura", "jogo trivia cultura conhecimento"),
        ("QUIZ_GRUPO", "Quiz em Grupo", "jogo quiz grupo amigos festa"),
        ("QUIZ_INFANTIL", "Quiz Infantil", "jogo quiz crianças"),
    ],
    "GAME_WORD": [
        ("CACA_PALAVRAS", "Caça-Palavras", "jogo caça palavras"),
        ("FORCA_ANAGRAMA", "Forca e Anagrama", "jogo forca anagrama palavra"),
        ("PALAVRAS_CRUZADAS_WORD", "Palavras Cruzadas", "jogo palavras cruzadas"),
        ("SOLETRAR", "Soletrar", "jogo soletrar ortografia"),
    ],
    "FAMILY": [
        ("INFANTIL_FAMILY", "Jogos Infantis", "jogo infantil criança"),
        ("EDUCATIVO_FAMILY", "Educativos para Família", "jogo educativo família aprender"),
        ("MULTIPLAYER_FAMILY", "Multiplayer Família", "jogo multiplayer família junto"),
        ("PERSONAGENS_FAMILY", "Personagens e Licenciados", "jogo personagem desenho crianças"),
    ],
}


def _normalizar_codigos(selected_codes: object) -> set[str]:
    """Transforma lista/string CSV de categorias em set de códigos limpos."""
    if not selected_codes:
        return set()
    if isinstance(selected_codes, str):
        parts = selected_codes.replace(";", ",").split(",")
    else:
        try:
            parts = list(selected_codes)  # type: ignore[arg-type]
        except TypeError:
            parts = [str(selected_codes)]
    return {str(code).strip().upper() for code in parts if str(code).strip()}


def _normalizar_subcodigos(selected_subcodes: object) -> Dict[str, set[str]]:
    """Transforma lista/string CSV de tokens 'CATEGORIA::SUBCATEGORIA' em
    dict {categoria: {subcodigos selecionados}}."""
    resultado: Dict[str, set[str]] = {}
    if not selected_subcodes:
        return resultado
    if isinstance(selected_subcodes, str):
        parts = selected_subcodes.replace(";", ",").split(",")
    else:
        try:
            parts = list(selected_subcodes)  # type: ignore[arg-type]
        except TypeError:
            parts = [str(selected_subcodes)]
    for token in parts:
        token = str(token).strip()
        if not token or "::" not in token:
            continue
        cat_code, sub_code = token.split("::", 1)
        cat_code = cat_code.strip().upper()
        sub_code = sub_code.strip().upper()
        if not cat_code or not sub_code:
            continue
        resultado.setdefault(cat_code, set()).add(sub_code)
    return resultado


def selecionar_categorias(
    scope: str,
    selected_codes: object = None,
    selected_subcodes: object = None,
) -> List[Tuple[str, str, str]]:
    """Retorna categorias no formato (codigo, nome, termo).

    Regras:
    - TODAS sempre retorna apps + jogos, ignorando filtro fino (categoria e subcategoria).
    - APPS/JOGOS aceitam selected_codes como CSV/lista.
    - selected_codes vazio = todas as categorias daquele escopo.
    - selected_subcodes (tokens 'CATEGORIA::SUBCATEGORIA') refina o termo de busca
      dentro de uma categoria selecionada: em vez de um item genérico, gera um item
      por subcategoria marcada, mantendo o código real da categoria no Google Play.
    """
    scope = (scope or "TODAS").upper()
    selected = _normalizar_codigos(selected_codes)
    categorias: List[Tuple[str, str, str]] = []

    if scope == "APPS":
        categorias.extend(CATEGORIAS_APPS.values())
    elif scope == "JOGOS":
        categorias.extend(CATEGORIAS_JOGOS.values())
    else:
        categorias.extend(CATEGORIAS_APPS.values())
        categorias.extend(CATEGORIAS_JOGOS.values())
        return categorias

    if selected:
        categorias = [cat for cat in categorias if cat[0].upper() in selected]

    subselecionadas = _normalizar_subcodigos(selected_subcodes)
    if not subselecionadas:
        return categorias

    expandidas: List[Tuple[str, str, str]] = []
    for codigo, nome, termo in categorias:
        subs_marcadas = subselecionadas.get(codigo.upper())
        subcats_disponiveis = SUBCATEGORIAS.get(codigo.upper())
        if not subs_marcadas or not subcats_disponiveis:
            expandidas.append((codigo, nome, termo))
            continue
        encontrou = False
        for sub_code, sub_nome, sub_termo in subcats_disponiveis:
            if sub_code.upper() in subs_marcadas:
                expandidas.append((codigo, f"{nome} · {sub_nome}", sub_termo))
                encontrou = True
        if not encontrou:
            expandidas.append((codigo, nome, termo))

    return expandidas


def _subs_para_form(codigo: str) -> list[dict[str, str]]:
    return [
        {"code": sub_code, "name": sub_nome, "term": sub_termo}
        for sub_code, sub_nome, sub_termo in SUBCATEGORIAS.get(codigo.upper(), [])
    ]


def categorias_para_form() -> dict[str, list[dict[str, object]]]:
    """Formato amigável para dropdowns/checkboxes do dashboard web (com subcategorias)."""
    return {
        "apps": [
            {"code": code, "name": name, "term": term, "subs": _subs_para_form(code)}
            for code, name, term in CATEGORIAS_APPS.values()
        ],
        "games": [
            {"code": code, "name": name, "term": term, "subs": _subs_para_form(code)}
            for code, name, term in CATEGORIAS_JOGOS.values()
        ],
    }
