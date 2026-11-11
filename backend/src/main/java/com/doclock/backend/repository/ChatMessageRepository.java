package com.doclock.backend.repository;
import com.doclock.backend.entity.*; import org.springframework.data.jpa.repository.JpaRepository; import java.util.List;
public interface ChatMessageRepository extends JpaRepository<ChatMessage,Long>{ List<ChatMessage> findByConversationIdOrderByTimestampAsc(Long id); }
