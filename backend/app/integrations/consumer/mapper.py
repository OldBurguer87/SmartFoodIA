from __future__ import annotations
from datetime import timedelta, timezone
from decimal import Decimal
from app.models.integration import StoreIntegration
from app.models.order import Order

class ConsumerContractError(ValueError): pass

def _iso(value): return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')

def _require_code(code: str | None, label: str) -> str:
    value=(code or '').strip()
    if not value: raise ConsumerContractError(f'{label} sem código PDV (externalCode).')
    return value

def map_order(order: Order, integration: StoreIntegration) -> dict:
    items=[]
    for index,item in enumerate(order.items, start=1):
        modifiers=[]
        for mi,m in enumerate(item.modifiers, start=1):
            modifiers.append({'id':str(m.id),'index':mi,'externalCode':_require_code(m.modifier_external_code, f'Complemento {m.modifier_name}'),'name':m.modifier_name,'quantity':m.quantity,'unit':'UN','unitPrice':float(m.unit_price),'price':float(m.total_price),'addition':0})
        items.append({'id':str(item.id),'uniqueId':str(item.id),'index':index,'externalCode':_require_code(item.product_external_code, f'Produto {item.product_name}'),'name':item.product_name,'quantity':item.quantity,'unit':'UN','unitPrice':float(item.unit_price),'price':float(item.total_price),'totalPrice':float(item.total_price),'observations':item.observations,'optionsPrice':float(sum(m.total_price for m in item.modifiers)),'addition':0,'options':modifiers or None})
    prepaid=order.total if order.payment_type=='PREPAID' else Decimal('0')
    pending=Decimal('0') if order.payment_type=='PREPAID' else order.total
    delivery=None; takeout=None
    if order.service_mode=='DELIVERY':
        required={'state':order.address_state,'city':order.address_city,'street':order.address_street,'number':order.address_number,'neighborhood':order.address_neighborhood}
        missing=[k for k,v in required.items() if not v]
        if missing: raise ConsumerContractError('Endereço delivery incompleto: '+', '.join(missing)+'.')
        delivery={'mode':'DEFAULT','pickupCode':order.display_id,'deliveredBy':'MERCHANT','deliveryDateTime':_iso(order.created_at+timedelta(minutes=45)),'deliveryAddress':{'country':'BR','state':order.address_state,'city':order.address_city,'postalCode':order.address_postal_code or '','streetName':order.address_street,'streetNumber':order.address_number,'neighborhood':order.address_neighborhood,'complement':order.address_complement,'reference':order.address_reference}}
    else:
        takeout={'mode':'DEFAULT','takeoutDateTime':_iso(order.created_at+timedelta(minutes=30))}
    method={'method':order.payment_method,'type':order.payment_type,'currency':'BRL','value':float(order.total),'prepaid':order.payment_type=='PREPAID','cash':({'changeFor':float(order.change_for)} if order.payment_method=='CASH' and order.change_for is not None else None),'card':None,'wallet':None}
    return {'item':{'id':str(order.id),'displayId':order.display_id,'orderType':order.service_mode,'salesChannel':'PARTNER','orderTiming':'IMMEDIATE','createdAt':_iso(order.created_at),'preparationStartDateTime':_iso(order.created_at),'merchant':{'id':integration.merchant_external_id,'name':integration.merchant_name},'items':items,'total':{'subTotal':float(order.subtotal),'deliveryFee':float(order.delivery_fee),'orderAmount':float(order.total),'benefits':float(order.discount),'additionalFees':0},'payments':{'methods':[method],'pending':float(pending),'prepaid':float(prepaid)},'customer':{'id':str(order.customer_id),'name':order.customer_name,'phone':{'number':order.customer_phone,'localizer':order.display_id,'localizerExpiration':_iso(order.created_at+timedelta(hours=1))},'documentNumber':None},'delivery':delivery,'takeout':takeout,'indoor':None,'schedule':None,'extraInfo':None},'statusCode':0,'reasonPhrase':None}
