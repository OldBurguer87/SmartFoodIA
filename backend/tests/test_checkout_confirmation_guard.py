from types import SimpleNamespace

from app.ai.orchestrator import _checkout_required_by_customer


def test_sim_after_posso_finalizar_assim_requires_checkout():
    history = [
        SimpleNamespace(
            sender_type="OLIVIA",
            content=(
                "Resumo do pedido: 1x X SALADA. "
                "Pagamento: R$ 5,00 em dinheiro e R$ 5,00 no PIX. "
                "Posso finalizar assim?"
            ),
        )
    ]

    assert _checkout_required_by_customer(
        history=history,
        customer_message="Sim",
    ) is True


def test_sim_without_confirmation_question_does_not_force_checkout():
    history = [
        SimpleNamespace(
            sender_type="OLIVIA",
            content="Quer acrescentar uma bebida ou acompanhamento?",
        )
    ]

    assert _checkout_required_by_customer(
        history=history,
        customer_message="Sim",
    ) is False


def test_mixed_pix_instructions_use_only_pix_component():
    from uuid import uuid4
    from app.ai.orchestrator import _pix_payment_instructions

    rules = SimpleNamespace(
        pix_key="oldburguer87@gmail.com",
        pix_receiver_name="Old Burguer 87",
        pix_receiver_institution=None,
    )
    db = SimpleNamespace(scalar=lambda statement: rules)

    text, _ = _pix_payment_instructions(
        db,
        store_id=uuid4(),
        order_data={
            "payment_method": "MIXED",
            "total": 10.00,
            "payments": [
                {"method": "PIX", "amount": 5.00},
                {"method": "CASH", "amount": 5.00},
            ],
        },
    )

    assert "Valor: R$ 5,00" in text
    assert "Valor: R$ 10,00" not in text


def test_simple_pix_instructions_keep_order_total():
    from uuid import uuid4
    from app.ai.orchestrator import _pix_payment_instructions

    rules = SimpleNamespace(
        pix_key="oldburguer87@gmail.com",
        pix_receiver_name="Old Burguer 87",
        pix_receiver_institution=None,
    )
    db = SimpleNamespace(scalar=lambda statement: rules)

    text, _ = _pix_payment_instructions(
        db,
        store_id=uuid4(),
        order_data={
            "payment_method": "PIX",
            "total": 10.00,
            "payments": [],
        },
    )

    assert "Valor: R$ 10,00" in text
