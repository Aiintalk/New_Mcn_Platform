import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function OperatorIntakePage() {
  const navigate = useNavigate();
  useEffect(() => {
    navigate('/workspace/kol-intake/chat', { replace: true });
  }, [navigate]);
  return null;
}
