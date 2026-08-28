---
description: Regra estrita sobre modificação de código e aprovação prévia
---

# Regra de Planejamento e Modificação de Código

Esta regra é absoluta e não deve ser quebrada em hipótese alguma durante o desenvolvimento deste projeto.

SEMPRE antes de programar ou alterar qualquer coisa no código da aplicação:
1. O agente DEVE obrigatoriamente apresentar um plano de implementação detalhado (usando o artefato `implementation_plan.md`).
2. O agente está ESTRITAMENTE PROIBIDO de iniciar a execução do plano, editar arquivos ou rodar comandos de alteração até que o usuário **aprove o plano de forma explícita digitando um texto afirmativo no chat**.
3. O agente não deve presumir aprovação automática em nenhuma circunstância. Deve-se parar a execução e aguardar a resposta em texto do usuário.
