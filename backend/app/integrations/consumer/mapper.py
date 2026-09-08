from __future__ import annotations
from datetime import timedelta, timezone
from decimal import Decimal
from uuid import uuid5
from app.models.integration import StoreIntegration
from app.models.order import Order
from app.services.order_payments import payment_parts_from_order

class ConsumerContractError(ValueError): pass

def _iso(value): return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

def _require_code(code: str | None, label: str) -> str:
    value=(code or '').strip()
    if not value: raise ConsumerContractError(f'{label} sem código PDV (externalCode).')
    return value

def map_order(order: Order, integration: StoreIntegration) -> dict:
    items=[]
    consumer_index=1

    for item in order.items:
        combo_components = list(item.combo_components)
        is_composed_combo = bool(combo_components)

        combo_total = sum(
            (
                component.total_price
                for component in combo_components
            ),
            Decimal("0.00"),
        )

        modifiers_total = sum(
            (
                modifier.total_price
                for modifier in item.modifiers
            ),
            Decimal("0.00"),
        )

        if is_composed_combo and combo_total != item.unit_price:
            raise ConsumerContractError(
                "Composição do combo "
                f"{item.product_name} ({item.product_external_code}) "
                f"soma R$ {combo_total:.2f}, mas o preço-base "
                f"do pedido é R$ {item.unit_price:.2f}."
            )

        # Produto normal mantém uma única linha, inclusive quantity > 1.
        # Combo composto é expandido em linhas quantity=1 para evitar
        # ambiguidade no cálculo das options pelo Consumer.
        repetitions = item.quantity if is_composed_combo else 1

        for repetition in range(1, repetitions + 1):
            options=[]
            option_index=1

            if is_composed_combo:
                if repetition == 1:
                    consumer_item_id = str(item.id)
                else:
                    consumer_item_id = str(
                        uuid5(
                            item.id,
                            f"consumer-combo-{repetition}",
                        )
                    )

                for component in combo_components:
                    if repetition == 1:
                        option_id = str(component.id)
                    else:
                        option_id = str(
                            uuid5(
                                component.id,
                                f"consumer-combo-{repetition}",
                            )
                        )

                    options.append({
                        'id': option_id,
                        'index': option_index,
                        'externalCode': _require_code(
                            component.component_external_code,
                            f'Componente {component.component_name}',
                        ),
                        'name': component.component_name,
                        'quantity': component.quantity,
                        'unit': 'UN',
                        'unitPrice': float(component.unit_price),
                        'price': float(component.total_price),
                        'addition': 0,
                    })
                    option_index += 1

                for modifier in item.modifiers:
                    if repetition == 1:
                        option_id = str(modifier.id)
                    else:
                        option_id = str(
                            uuid5(
                                modifier.id,
                                f"consumer-combo-{repetition}",
                            )
                        )

                    options.append({
                        'id': option_id,
                        'index': option_index,
                        'externalCode': _require_code(
                            modifier.modifier_external_code,
                            f'Complemento {modifier.modifier_name}',
                        ),
                        'name': modifier.modifier_name,
                        'quantity': modifier.quantity,
                        'unit': 'UN',
                        'unitPrice': float(modifier.unit_price),
                        'price': float(modifier.total_price),
                        'addition': 0,
                    })
                    option_index += 1

                per_unit_total = (
                    item.unit_price + modifiers_total
                )

                items.append({
                    'id': consumer_item_id,
                    'uniqueId': consumer_item_id,
                    'index': consumer_index,
                    'externalCode': _require_code(
                        item.product_external_code,
                        f'Produto {item.product_name}',
                    ),
                    'name': item.product_name,
                    'quantity': 1,
                    'unit': 'UN',
                    'unitPrice': 0.0,
                    'price': 0.0,
                    'totalPrice': float(per_unit_total),
                    'observations': item.observations,
                    'optionsPrice': float(
                        combo_total + modifiers_total
                    ),
                    'addition': 0,
                    'options': options or None,
                })

                consumer_index += 1
                continue

            # Produto normal: contrato anterior permanece intacto.
            for modifier in item.modifiers:
                options.append({
                    'id': str(modifier.id),
                    'index': option_index,
                    'externalCode': _require_code(
                        modifier.modifier_external_code,
                        f'Complemento {modifier.modifier_name}',
                    ),
                    'name': modifier.modifier_name,
                    'quantity': modifier.quantity,
                    'unit': 'UN',
                    'unitPrice': float(modifier.unit_price),
                    'price': float(modifier.total_price),
                    'addition': 0,
                })
                option_index += 1

            items.append({
                'id': str(item.id),
                'uniqueId': str(item.id),
                'index': consumer_index,
                'externalCode': _require_code(
                    item.product_external_code,
                    f'Produto {item.product_name}',
                ),
                'name': item.product_name,
                'quantity': item.quantity,
                'unit': 'UN',
                'unitPrice': float(item.unit_price),
                'price': float(item.total_price),
                'totalPrice': float(item.total_price),
                'observations': item.observations,
                'optionsPrice': float(modifiers_total),
                'addition': 0,
                'options': options or None,
            })

            consumer_index += 1

    payment_parts = payment_parts_from_order(order)

    payment_methods = []
    prepaid = Decimal("0.00")
    pending = Decimal("0.00")

    for payment in payment_parts:
        is_prepaid = (
            payment.method == "PIX"
            or payment.payment_type == "PREPAID"
        )

        if is_prepaid:
            prepaid += payment.amount
        else:
            pending += payment.amount

        payment_methods.append(
            {
                "method": payment.method,
                "type": "ONLINE" if is_prepaid else "OFFLINE",
                "currency": "BRL",
                "value": float(payment.amount),
                "prepaid": is_prepaid,
                "cash": (
                    {
                        "changeFor": float(payment.change_for)
                    }
                    if (
                        payment.method == "CASH"
                        and payment.change_for is not None
                    )
                    else None
                ),
                "card": None,
                "wallet": None,
            }
        )

    delivery=None; takeout=None
    if order.service_mode=='DELIVERY':
        required={'state':order.address_state,'city':order.address_city,'street':order.address_street,'number':order.address_number,'neighborhood':order.address_neighborhood}
        missing=[k for k,v in required.items() if not v]
        if missing: raise ConsumerContractError('Endereço delivery incompleto: '+', '.join(missing)+'.')
        formatted_address = (
            f"{order.address_street}, {order.address_number}, "
            f"{order.address_neighborhood} - {order.address_city}/{order.address_state}"
        )
        delivery = {
            'mode': 'DEFAULT',
            'pickupCode': order.display_id,
            'deliveredBy': 'Partner',
            'deliveryDateTime': _iso(order.created_at + timedelta(minutes=45)),
            'deliveryAddress': {
                'country': 'BR',
                'state': order.address_state,
                'city': order.address_city,
                'postalCode': order.address_postal_code or '',
                'streetName': order.address_street,
                'formattedAddress': formatted_address,
                'streetNumber': order.address_number,
                'coordinates': {
                    'latitude': 0,
                    'longitude': 0,
                },
                'neighborhood': order.address_neighborhood,
                'complement': order.address_complement,
                'reference': order.address_reference,
            },
            'observations': None,
        }
    else:
        takeout={'mode':'DEFAULT','takeoutDateTime':_iso(order.created_at+timedelta(minutes=30))}
    return {'item':{'id':str(order.id),'displayId':order.display_id,'orderType':order.service_mode,'salesChannel':'PARTNER','orderTiming':'IMMEDIATE','createdAt':_iso(order.created_at),'preparationStartDateTime':_iso(order.created_at),'merchant':{'id':integration.merchant_external_id,'name':integration.merchant_name},'items':items,'total':{'subTotal':float(order.subtotal),'deliveryFee':float(order.delivery_fee),'orderAmount':float(order.total),'benefits':float(order.discount),'additionalFees':0},'payments':{'methods':payment_methods,'pending':float(pending),'prepaid':float(prepaid)},'customer':{'id':str(order.customer_id),'name':order.customer_name,'phone':{'number':order.customer_phone,'localizer':order.display_id,'localizerExpiration':_iso(order.created_at+timedelta(hours=1))},'documentNumber':None},'delivery':delivery,'takeout':takeout,'indoor':None,'schedule':None,'extraInfo':None},'statusCode':0,'reasonPhrase':None}
