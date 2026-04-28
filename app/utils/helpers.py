from app.models.service import Service, ServiceRead


def service_response(service: Service) -> ServiceRead:
    return ServiceRead(**service.to_public_dict())


def services_response(services: list[Service]) -> list[ServiceRead]:
    return [service_response(service) for service in services]
