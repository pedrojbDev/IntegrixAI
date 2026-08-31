from __future__ import annotations


# Canonical values follow the vocabulary expected by the PB Saude provider.
# Aliases are normalized by catalog.py, so accents, case and punctuation do not
# need to be duplicated here.
DEFAULT_SPECIALTY_ALIASES: dict[str, tuple[str, ...]] = {
    "GINECOLOGIA": ("gineco", "ginecologista", "medica de mulher", "medico de mulher"),
    "CARDIOLOGIA": ("cardio", "cardiologista", "medico do coracao"),
    "ORTOPEDIA": ("ortoped", "ortopedista", "medico dos ossos", "medico do joelho"),
    "PEDIATRIA": ("pediatra", "medico de crianca", "medico infantil"),
    "DERMATOLOGIA": ("dermato", "dermatologista", "medico de pele"),
    "OFTALMOLOGIA": ("oftalmo", "oftalmologista", "medico dos olhos", "medico de vista"),
    "OTORRINOLARINGOLOGIA": (
        "otorrino", "otorrinolaringologista", "medico de ouvido", "medico de nariz e garganta",
    ),
    "NEUROLOGIA": ("neurologista", "medico dos nervos"),
    "NEUROCIRURGIA": ("neurocirurgiao", "neurocirurgiã"),
    "ENDOCRINOLOGIA": ("endocrino", "endocrinologista", "medico de hormonio", "medico de tireoide"),
    "GASTROENTEROLOGIA": ("gastro", "gastroenterologista", "medico do estomago"),
    "UROLOGIA": ("uro", "urologista", "medico da prostata"),
    "PSIQUIATRIA": ("psiquiatra", "medico de saude mental"),
    "PSICOLOGIA": ("psicologo", "psicologa", "psico"),
    "NUTRICAO": ("nutri", "nutricionista"),
    "FONOAUDIOLOGIA": ("fono", "fonoaudiologo", "fonoaudiologa"),
    "FISIOTERAPIA": ("fisio", "fisioterapeuta"),
    "REUMATOLOGIA": ("reumato", "reumatologista", "medico das articulacoes"),
    "PNEUMOLOGIA": ("pneumo", "pneumologista", "medico do pulmao"),
    "NEFROLOGIA": ("nefro", "nefrologista", "medico dos rins"),
    "HEMATOLOGIA": ("hemato", "hematologista", "medico do sangue"),
    "ONCOLOGIA": ("onco", "oncologista", "medico de cancer"),
    "INFECTOLOGIA": ("infecto", "infectologista"),
    "ALERGOLOGIA": ("alergista", "alergologista", "medico de alergia"),
    "IMUNOLOGIA": ("imunologista",),
    "GERIATRIA": ("geriatra", "medico de idoso"),
    "COLOPROCTOLOGIA": ("procto", "proctologista", "coloproctologista"),
    "MASTOLOGIA": ("masto", "mastologista", "medico da mama"),
    "ANGIOLOGIA": ("angiologista",),
    "CIRURGIA VASCULAR": ("cirurgiao vascular", "cirurgia de vasos"),
    "CLINICA MEDICA": ("clinico", "clinico geral", "medico geral"),
    "CIRURGIA GERAL": ("cirurgiao geral",),
    "CIRURGIA BUCOMAXILOFACIAL": ("buco", "bucomaxilo", "cirurgiao bucomaxilofacial"),
    "LABORATORIO": ("exames laboratoriais", "exame de sangue", "coleta de sangue", "onde faco coleta"),
    "DIAGNOSTICO POR IMAGEM": ("clinica de imagem", "servico de diagnostico por imagem"),
    "RESSONANCIA MAGNETICA": ("ressonancia",),
    "TOMOGRAFIA COMPUTADORIZADA": ("tomografia",),
    "ULTRASSONOGRAFIA": ("ultrassom",),
    "RADIOLOGIA": ("raio x", "raio-x", "radiografia"),
    "MAMOGRAFIA": (),
    "ENDOSCOPIA": (),
    "COLONOSCOPIA": (),
    "HOSPITAL": ("hospital da rede",),
    "PRONTO ATENDIMENTO": ("pronto socorro", "emergencia hospitalar"),
    "MATERNIDADE": ("hospital para parto",),
}


AMBIGUOUS_SPECIALTY_TERMS = {
    "cirurgiao", "medico da coluna", "medico de circulacao", "neuro", "terapeuta", "vascular",
}
