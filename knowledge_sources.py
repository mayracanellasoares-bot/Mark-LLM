"""Índice de referência empacotado com o serviço; links não são conteúdo verificado."""
import re
import unicodedata


SOURCES = {
    'juridico': (
        'Legislação federal compilada: https://www4.planalto.gov.br/legislacao/ ; '
        'Constituição: https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm ; '
        'STF, precedentes e repercussão geral: https://portal.stf.jus.br/repercussaogeral/ ; '
        'STJ, decisões e súmulas: https://scon.stj.jus.br/SCON/ ; '
        'TST, jurisprudência trabalhista: https://www.tst.jus.br/jurisprudencia'
    ),
    'literatura': (
        'Wikisource: https://pt.wikisource.org/ ; '
        'Project Gutenberg: https://www.gutenberg.org/ ; '
        'Open Library: https://openlibrary.org/'
    ),
    'gramatica': 'Academia Brasileira de Letras, VOLP: https://www.academia.org.br/nossa-lingua/busca-no-vocabulario',
    'humanas': 'IBGE, estatísticas: https://sidra.ibge.gov.br/ ; artigos científicos: https://www.scielo.br/',
    'exatas': 'Artigos científicos: https://www.scielo.br/ ; NIST, constantes e medidas: https://physics.nist.gov/cuu/Constants/',
}


def assunto(pergunta: str) -> str | None:
    plain = unicodedata.normalize('NFKD', pergunta.lower())
    plain = ''.join(c for c in plain if not unicodedata.combining(c))
    checks = (
        ('juridico', r'\b(lei|leis|legislacao|jurisprudencia|sumula|acordao|sentenca|tribunal|stf|stj|tst|trt|clt|cpc|cf|fgts|inss|resolucao cnj|codigo civil|codigo penal|processo judicial|juridic\w*|constitucional\w*|direito|art(?:igo)?\.? \d+)\b'),
        ('gramatica', r'\b(gramatica|ortografia|concordancia|regencia|acentuacao|pontuacao|crase|verbo|substantivo)\b'),
        ('literatura', r'\b(literatura|romance|poesia|poema|conto|escritor\w*|autor\w*|livro|obra literaria)\b'),
        ('humanas', r'\b(historia|geografia|sociologia|filosofia|antropologia|economia|populacao|demografia)\b'),
        ('exatas', r'\b(matematica|fisica|quimica|calculo|equacao|geometria|estatistica|algebra)\b'),
    )
    return next((area for area, pattern in checks if re.search(pattern, plain)), None)


def guia(pergunta: str) -> tuple[str | None, str]:
    area = assunto(pergunta)
    if not area:
        return None, ''
    guidance = 'Índice de fontes para orientar pesquisa (os links, isoladamente, não comprovam afirmações): ' + SOURCES[area]
    if area == 'juridico':
        guidance += (' Consulte a redação vigente, alterações e datas. Distinga texto legal, interpretação jurisprudencial '
                     'e aplicação prática; verifique órgão, número, data e eventual superação de precedentes. '
                     'Cite URLs específicas das normas e decisões efetivamente consultadas. Se não conseguir verificar, diga isso claramente.')
    else:
        guidance += ' Prefira fontes primárias quando a informação for atual ou controversa e cite a página realmente consultada.'
    return area, guidance
