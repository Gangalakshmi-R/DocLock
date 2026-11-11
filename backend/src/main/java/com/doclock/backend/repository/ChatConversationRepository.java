package com.doclock.backend.repository;
import com.doclock.backend.entity.*; import org.springframework.data.jpa.repository.JpaRepository; import java.util.List;
public interface ChatConversationRepository extends JpaRepository<ChatConversation,Long>{ List<ChatConversation> findAllByOrderByUpdatedAtDesc(); }
