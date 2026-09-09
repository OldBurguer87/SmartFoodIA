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
