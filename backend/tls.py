"""Verified outbound TLS with public roots and installed system roots."""

import ssl

import certifi


def outbound_tls():
    context = ssl.create_default_context(cafile=certifi.where())
    # Add system roots without replacing certifi's public roots. Certificate
    # validation and hostname checks remain enabled for every request.
    context.load_default_certs()
    return context
