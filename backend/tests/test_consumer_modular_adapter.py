from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.base import Base
from app.integrations.consumer.adapter import ConsumerPartnerAdapter
from app.integrations.consumer.mapper import ConsumerContractError
from app.models.catalog import Company, Product, Store
from app.models.integration import StoreIntegration
from app.schemas.cart import CartItemAdd
from app.schemas.customer import CustomerCreate, AddressCreate
from app.schemas.order import CheckoutRequest
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.customer import CustomerService


def setup(code='235'):
    db=Session(create_engine('sqlite+pysqlite:///:memory:')); Base.metadata.create_all(db.get_bind())
    c=Company(name='Old'); db.add(c); db.flush(); s=Store(company_id=c.id,name='Old',slug=f'old-{uuid4()}',city='Coari',state='AM',timezone='America/Manaus'); db.add(s); db.flush(); integ=StoreIntegration(store_id=s.id,provider='CONSUMER',token_hash='x'*64,merchant_external_id='m1',merchant_name='Old',active=True); db.add(integ); p=Product(store_id=s.id,external_code=code,name='Monster',price=Decimal('60'),active=True,available_for_delivery=True,available_for_takeout=True); db.add(p); db.commit()
    cust=CustomerService().find_or_create(db,CustomerCreate(store_id=s.id,name='Cliente',phone='97999999999')); addr=CustomerService().add_address(db,customer_id=cust.id,payload=AddressCreate(street='Rua',number='1',neighborhood='Centro',city='Coari',state='AM')); cart=CartService().create_or_get_open(db,store_id=s.id,customer_id=cust.id,service_mode='DELIVERY'); CartService().add_item(db,cart_id=cart.id,payload=CartItemAdd(product_external_code=code,quantity=1)); order=CheckoutService().checkout(db,cart_id=cart.id,payload=CheckoutRequest(address_id=addr.id,payment_method='PIX',delivery_fee=Decimal('5')))
    return db,s,integ,order

def test_core_marks_order_ready_for_any_integration():
    db,s,i,o=setup(); assert o.status=='READY_FOR_INTEGRATION'; assert ConsumerPartnerAdapter().poll(db,store_id=s.id)[0].code=='PLC'

def test_adapter_maps_consumer_contract():
    db,s,i,o=setup(); payload=ConsumerPartnerAdapter().serialize_order(db,store_id=s.id,order_id=o.id,integration=i); assert payload['item']['salesChannel']=='PARTNER'; assert payload['item']['items'][0]['externalCode']=='235'; assert payload['item']['total']['orderAmount']==65.0

def test_mapper_rejects_missing_pdv_code():
    db,s,i,o=setup(); persisted=ConsumerPartnerAdapter().orders.get(db,o.id); persisted.items[0].product_external_code=''; db.commit()
    with pytest.raises(ConsumerContractError): ConsumerPartnerAdapter().serialize_order(db,store_id=s.id,order_id=o.id,integration=i)

def test_status_is_idempotent():
    db,s,i,o=setup(); adapter=ConsumerPartnerAdapter(); assert adapter.apply_external_status(db,store_id=s.id,order_id=o.id,status='CONFIRMED')[1] is True; assert adapter.apply_external_status(db,store_id=s.id,order_id=o.id,status='CONFIRMED')[1] is False
