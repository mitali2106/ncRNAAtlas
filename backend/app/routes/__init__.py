"""REST API blueprints."""


def register_blueprints(app):
    from .admin import bp as admin_bp
    from .associations import bp as associations_bp
    from .diseases import bp as diseases_bp
    from .genes import bp as genes_bp
    from .literature import bp as literature_bp
    from .meta import bp as meta_bp
    from .ncrnas import bp as ncrnas_bp
    from .network import bp as network_bp
    from .pathways import bp as pathways_bp
    from .search import bp as search_bp

    for bp in (meta_bp, ncrnas_bp, diseases_bp, genes_bp, associations_bp, literature_bp, pathways_bp,
               network_bp, search_bp, admin_bp):
        app.register_blueprint(bp, url_prefix="/api")
