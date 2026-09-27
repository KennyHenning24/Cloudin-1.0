"""App retirada: Cloudin Reservas.

Cloudin quedó enfocado en el menú digital, los pedidos por QR, las mesas y los
meseros. De esta app solo quedan sus migraciones: la última borra sus tablas, así
las bases que ya existían se actualizan sin romperse y las nuevas quedan igual.
No le agregues código. Ver «Apps retiradas» en CONTEXTO-PARA-CODEX.md.
"""

import secrets

ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def nuevo_codigo() -> str:
    """La usa la migración 0001 como valor por defecto: tiene que seguir existiendo."""
    return "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(6))
