import os
import re
from collections.abc import Callable
from functools import wraps
from html import escape
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlsplit

from fladgejt.login import create_client
from flask import Flask, Response, redirect, request, session, url_for
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
from onelogin.saml2.settings import OneLogin_Saml2_Settings

F = TypeVar("F", bound=Callable)

ROOT_URL = os.environ["ROOT_URL"].rstrip("/") + "/"
AIS_URL = os.environ.get("AIS_URL", "https://ais2.uniba.sk/")
ANDRVOTR_API_KEY = os.environ.get("ANDRVOTR_API_KEY")

TOKEN_ATTR = "tag:fmfi-svt.github.io,2024:andrvotr-authority-token"
UID_ATTR = "urn:oid:0.9.2342.19200300.100.1.1"
NAMEFORMAT_URI = "urn:oasis:names:tc:SAML:2.0:attrname-format:uri"


def _env(name: str, default: str) -> str:
    """Read and XML-escape a env value."""
    return escape(os.environ.get(name, default), quote=True)


def _env_pem(name: str) -> str | None:
    """Read a PEM value from env, accepting escaped newlines."""
    value = os.environ.get(name)
    if not value:
        return None
    if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
        value = value[1:-1]
    return value.replace("\\n", "\n")


def _settings() -> OneLogin_Saml2_Settings:
    """Build python3-saml settings for this SP and Uniba IdP."""
    sp = {
        "entityId": ROOT_URL + "saml_sp",
        "assertionConsumerService": {"url": ROOT_URL + "saml_acs"},
        "singleLogoutService": {"url": ROOT_URL + "logout"},
    }
    if cert := _env_pem("SAML_SP_CERT"):
        sp["x509cert"] = cert
    if key := _env_pem("SAML_SP_KEY"):
        sp["privateKey"] = key

    settings = {
        "sp": sp,
        "security": {
            "metadataValidUntil": "",
            "metadataCacheDuration": "",
            "wantAssertionsEncrypted": True,
            "rejectDeprecatedAlgorithm": True,
            "logoutRequestSigned": True,
            "logoutResponseSigned": True,
        },
    }
    idp_metadata = Path("idp-metadata.xml").read_bytes()
    settings = OneLogin_Saml2_IdPMetadataParser.merge_settings(
        settings, OneLogin_Saml2_IdPMetadataParser.parse(idp_metadata)
    )
    return OneLogin_Saml2_Settings(settings=settings)


def _auth() -> OneLogin_Saml2_Auth:
    """Create a SAML auth helper for the current Flask request."""
    root = urlsplit(ROOT_URL)
    return OneLogin_Saml2_Auth(
        {
            "http_host": root.netloc,
            "script_name": request.path,
            "get_data": request.args,
            "post_data": request.form,
            "https": "on" if root.scheme == "https" else "off",
            "validate_signature_from_qs": True,
            "query_string": request.query_string.decode("ascii", "replace"),
        },
        old_settings=_settings(),
    )


def _one(auth: OneLogin_Saml2_Auth, name: str) -> str | None:
    """Return one SAML attribute value, or fail if duplicated."""
    values = auth.get_attribute(name)
    if not values:
        return None
    if len(values) != 1:
        raise RuntimeError(f"Multiple {name} attribute values")
    return values[0]


def require_login(func: F) -> F:
    """Redirect anonymous users to SAML login."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if "ais_cookies" not in session:
            session.clear()
            return redirect(url_for("andrvotr_login"))
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def _votr_server_conf(login_types):
    """Return Votr server config for AIS."""
    return {
        "title": AIS_URL,
        "login_types": login_types,
        "ais_cookie": "JSESSIONID",
        "ais_url": AIS_URL,
    }


def create_ais_client(andrvotr_authority_token: str):
    """Use an Andrvotr token to create a logged-in Votr client."""
    return create_client(
        _votr_server_conf(("saml_andrvotr",)),
        {
            "type": "saml_andrvotr",
            "my_entity_id": ROOT_URL + "saml_sp",
            "andrvotr_api_key": ANDRVOTR_API_KEY,
            "andrvotr_authority_token": andrvotr_authority_token,
        },
    )


def create_ais_context(andrvotr_authority_token: str):
    """Use an Andrvotr token to create a logged-in AIS context."""
    return create_ais_client(andrvotr_authority_token).context


def _cookie_string(client) -> str:
    """Serialize AIS cookies from a Votr client for Flask session storage."""
    ais_host = urlsplit(AIS_URL).hostname
    return "; ".join(
        f"{cookie.name}={cookie.value}"
        for cookie in client.context.requests_session.cookies
        if cookie.domain.lstrip(".") == ais_host
    )


def ais_context():
    """Recreate a logged-in AIS context from cookies in Flask session."""
    return create_client(
        _votr_server_conf(("cookie",)),
        {"type": "cookie", "ais_cookie": session["ais_cookies"]},
    ).context


def _uniba_metadata(metadata: bytes) -> bytes:
    """Patch generated SP metadata to match Uniba's metadata template."""
    name_sk = _env("SAML_SERVICE_NAME_SK", "Export záverečných prác")
    name_en = _env("SAML_SERVICE_NAME_EN", "Thesis export")
    desc_sk = _env("SAML_SERVICE_DESC_SK", "Export záverečných prác z AIS.")
    desc_en = _env("SAML_SERVICE_DESC_EN", "Thesis export from AIS.")
    info_url = _env("SAML_INFORMATION_URL", ROOT_URL)

    ui_info = f"""
    <md:Extensions>
      <mdui:UIInfo xmlns:mdui="urn:oasis:names:tc:SAML:metadata:ui">
        <mdui:DisplayName xml:lang="sk">{name_sk}</mdui:DisplayName>
        <mdui:DisplayName xml:lang="en">{name_en}</mdui:DisplayName>
        <mdui:Description xml:lang="sk">{desc_sk}</mdui:Description>
        <mdui:Description xml:lang="en">{desc_en}</mdui:Description>
        <mdui:InformationURL xml:lang="sk">{info_url}</mdui:InformationURL>
        <mdui:InformationURL xml:lang="en">{info_url}</mdui:InformationURL>
      </mdui:UIInfo>
    </md:Extensions>
"""
    requested_attrs = f'''
    <md:AttributeConsumingService index="0">
      <md:ServiceName xml:lang="sk">{name_sk}</md:ServiceName>
      <md:ServiceName xml:lang="en">{name_en}</md:ServiceName>
      <md:ServiceDescription xml:lang="sk">{desc_sk}</md:ServiceDescription>
      <md:ServiceDescription xml:lang="en">{desc_en}</md:ServiceDescription>
      <md:RequestedAttribute FriendlyName="uid" Name="{UID_ATTR}" NameFormat="{NAMEFORMAT_URI}" isRequired="true"/>
      <md:RequestedAttribute FriendlyName="andrvotr-authority-token" Name="{TOKEN_ATTR}" NameFormat="{NAMEFORMAT_URI}" isRequired="true"/>
    </md:AttributeConsumingService>
'''
    org = f"""
  <md:Organization>
    <md:OrganizationName xml:lang="sk">{_env("SAML_ORG_NAME_SK", "Fakulta matematiky, fyziky a informatiky UK")}</md:OrganizationName>
    <md:OrganizationName xml:lang="en">{_env("SAML_ORG_NAME_EN", "Faculty of Mathematics, Physics and Informatics, Comenius University")}</md:OrganizationName>
    <md:OrganizationDisplayName xml:lang="sk">{_env("SAML_ORG_DISPLAY_SK", "FMFI UK")}</md:OrganizationDisplayName>
    <md:OrganizationDisplayName xml:lang="en">{_env("SAML_ORG_DISPLAY_EN", "FMFI UK")}</md:OrganizationDisplayName>
    <md:OrganizationURL xml:lang="sk">{_env("SAML_ORG_URL_SK", "https://fmph.uniba.sk/")}</md:OrganizationURL>
    <md:OrganizationURL xml:lang="en">{_env("SAML_ORG_URL_EN", "https://fmph.uniba.sk/en/")}</md:OrganizationURL>
  </md:Organization>
  <md:ContactPerson contactType="technical">
    <md:GivenName>{_env("SAML_TECH_GIVEN_NAME", "ŠVT")}</md:GivenName>
    <md:SurName>{_env("SAML_TECH_SURNAME", "FMFI UK")}</md:SurName>
    <md:EmailAddress>mailto:{_env("SAML_TECH_EMAIL", "fmfi-svt@googlegroups.com")}</md:EmailAddress>
  </md:ContactPerson>
"""

    metadata = re.sub(rb" *<md:NameIDFormat>\S*</md:NameIDFormat>\n", b"", metadata)
    metadata = re.sub(
        rb"(<md:SPSSODescriptor\b[^>]*>)",
        lambda match: match.group(1) + ui_info.encode(),
        metadata,
        count=1,
    )
    metadata = metadata.replace(
        b"</md:SPSSODescriptor>",
        requested_attrs.encode() + b"  </md:SPSSODescriptor>",
        1,
    )
    return metadata.replace(
        b"</md:EntityDescriptor>", org.encode() + b"</md:EntityDescriptor>", 1
    )


def register(app: Flask) -> None:
    """Register SAML login, ACS, metadata, and logout routes on app."""

    @app.get("/saml_sp")
    def saml_sp():
        """Serve SP metadata for IdP registration."""
        settings = _settings()
        metadata = _uniba_metadata(settings.get_sp_metadata())
        errors = settings.validate_metadata(metadata)
        if errors:
            raise RuntimeError(repr(errors))
        return Response(metadata, content_type="application/samlmetadata+xml")

    @app.get("/login")
    def andrvotr_login():
        """Start browser SAML login at the IdP."""
        auth = _auth()
        redirect_url = auth.login(return_to=ROOT_URL)
        session["saml_request_id"] = auth.get_last_request_id()
        return redirect(redirect_url)

    @app.post("/saml_acs")
    def saml_acs():
        """Finish SAML login and store AIS cookies in session."""
        auth = _auth()
        auth.process_response(request_id=session.pop("saml_request_id", None))
        errors = auth.get_errors()
        if errors:
            raise RuntimeError(
                f"SAML login failed: {errors!r}; {auth.get_last_error_reason()}"
            )

        token = _one(auth, TOKEN_ATTR)
        if not token:
            raise RuntimeError("IdP did not provide the Andrvotr authority token")

        session["ais_cookies"] = _cookie_string(create_ais_client(token))
        session["uid"] = _one(auth, UID_ATTR)
        return redirect(url_for("index"))

    @app.get("/logout")
    def logout():
        """Clear local Flask session."""
        session.clear()
        return redirect(url_for("index"))
