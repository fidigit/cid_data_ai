from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedWeComMessage:
    """由已验签、已解密的企业微信回调适配器产生的内部 DTO。"""

    message_id: str
    user_id: str
    user_name: str | None
    conversation_id: str | None
    text: str


class WeComOutboundGateway:
    """企业微信具体协议与凭证在确定智能机器人/自建应用模式后实现。"""

    def send_accepted(self, message: NormalizedWeComMessage, job_id: str) -> None:
        raise NotImplementedError("请先确定企业微信入口模式并完成官方回调验签/加解密接入。")

    def send_completed(self, message: NormalizedWeComMessage, artifact_url: str) -> None:
        raise NotImplementedError("请先实现企业微信文件上传或短期签名下载链接回传。")

